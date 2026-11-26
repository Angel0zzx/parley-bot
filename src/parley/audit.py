"""
Nightly audit: resolve pending predictions against football-data.org results and
report hit rate / ROI to Telegram.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from parley.config import DATABASE_URL, TELEGRAM_FREE_CHAT_ID, TELEGRAM_VIP_CHAT_ID
from parley.db.repository import (
    calcular_stats,
    get_pending_predictions,
    get_stats,
    update_prediction,
)
from parley.notifiers.telegram import get_audit_targets, send_telegram
from parley.providers.football_data import FootballDataProvider

log = logging.getLogger("parley.audit")


def evaluar_pick(mercado: str, seleccion: str, home_goals: int, away_goals: int) -> Optional[str]:
    """Return GANADA/PERDIDA/NULA for a pick given the final score, or None if unsupported."""
    if home_goals is None or away_goals is None:
        return None

    total = home_goals + away_goals
    mercado = (mercado or "").strip()
    seleccion = (seleccion or "").strip()

    if mercado == "1X2":
        if seleccion.startswith("Local"):
            return "GANADA" if home_goals > away_goals else "PERDIDA"
        if seleccion.startswith("Empate"):
            return "GANADA" if home_goals == away_goals else "PERDIDA"
        if seleccion.startswith("Visitante"):
            return "GANADA" if away_goals > home_goals else "PERDIDA"
        return None

    if mercado == "Doble Oportunidad":
        if seleccion.startswith("1X"):
            return "GANADA" if home_goals >= away_goals else "PERDIDA"
        if seleccion.startswith("X2"):
            return "GANADA" if away_goals >= home_goals else "PERDIDA"
        return None

    if mercado == "DNB":
        if home_goals == away_goals:
            return "NULA"
        if seleccion.startswith("Local"):
            return "GANADA" if home_goals > away_goals else "PERDIDA"
        if seleccion.startswith("Visitante"):
            return "GANADA" if away_goals > home_goals else "PERDIDA"
        return None

    if mercado == "Goles":
        parts = seleccion.split()
        if len(parts) != 2:
            return None
        side = parts[0].lower()
        try:
            linea = float(parts[1])
        except ValueError:
            return None
        if total == linea:
            return "NULA"
        if side == "over":
            return "GANADA" if total > linea else "PERDIDA"
        if side == "under":
            return "GANADA" if total < linea else "PERDIDA"
        return None

    if mercado == "BTTS":
        ambos = home_goals > 0 and away_goals > 0
        marcador = seleccion.split(":")[-1].strip().upper()
        if marcador == "NO":
            return "PERDIDA" if ambos else "GANADA"
        return "GANADA" if ambos else "PERDIDA"

    return None


def build_audit_message(
    evaluadas: List[Dict[str, Any]],
    sin_resolver: int,
    stats_global: Dict[str, Any],
    fecha_str: str,
) -> str:
    """Build the nightly HTML summary for Telegram."""
    r = calcular_stats(evaluadas)
    lines = [f"🌙 <b>AUDITORÍA NOCTURNA — {fecha_str}</b>", ""]

    if evaluadas:
        lines += [
            "📋 <b>Resultados de esta auditoría</b>",
            f"✅ Ganadas: <b>{r['ganadas']}</b>",
            f"❌ Perdidas: <b>{r['perdidas']}</b>",
            f"⚪ Nulas: <b>{r['nulas']}</b>",
            f"🎯 Acierto: <b>{r['acierto_pct']:.1f}%</b>",
            f"💵 ROI: <b>{r['roi_pct']:+.1f}%</b>",
        ]
    else:
        lines.append("ℹ️ No se resolvieron picks en esta auditoría.")

    if sin_resolver:
        lines.append(f"⏳ Sin resultado aún: <b>{sin_resolver}</b>")

    lines += [
        "",
        "📊 <b>ACUMULADO HISTÓRICO</b>",
        f"Resueltas: <b>{stats_global['total']}</b> "
        f"(✅ {stats_global['ganadas']} · ❌ {stats_global['perdidas']} · ⚪ {stats_global['nulas']})",
        f"Acierto: <b>{stats_global['acierto_pct']:.1f}%</b>",
        f"ROI: <b>{stats_global['roi_pct']:+.1f}%</b>",
    ]
    return "\n".join(lines)


def run_audit(
    fd_key: str,
    tg_token: str,
    tg_chat_id: str,
    tz=None,
    debug: bool = False,
    database_url: Optional[str] = None,
    free_chat_id: Optional[str] = None,
    vip_chat_id: Optional[str] = None,
) -> None:
    """Resolve pending predictions, persist results and send the nightly summary."""
    db_url = database_url if database_url is not None else DATABASE_URL
    if not db_url:
        log.warning("DATABASE_URL no configurada; se omite la auditoría nocturna.")
        return
    if not fd_key:
        log.error("Falta FOOTBALL_DATA_KEY para consultar resultados finales.")
        return

    vip = vip_chat_id if vip_chat_id is not None else TELEGRAM_VIP_CHAT_ID
    free = free_chat_id if free_chat_id is not None else TELEGRAM_FREE_CHAT_ID
    targets = get_audit_targets(vip, free, tg_chat_id)

    hoy = datetime.now(tz).date() if tz else date.today()
    pendientes = get_pending_predictions(hasta=hoy, database_url=db_url)
    log.info("Predicciones pendientes: %d", len(pendientes))

    resultados: Dict[str, Dict[str, Any]] = {}
    if pendientes:
        fechas = sorted({p["fecha"] for p in pendientes})
        inicio = fechas[0] - timedelta(days=1)
        fin = fechas[-1] + timedelta(days=1)
        provider = FootballDataProvider(fd_key)
        cursor = inicio
        while cursor <= fin:
            bloque_fin = min(cursor + timedelta(days=9), fin)
            resultados.update(
                provider.get_results(
                    cursor.strftime("%Y-%m-%d"),
                    bloque_fin.strftime("%Y-%m-%d"),
                )
            )
            cursor = bloque_fin + timedelta(days=1)

    evaluadas: List[Dict[str, Any]] = []
    sin_resolver = 0
    for pendiente in pendientes:
        resultado = resultados.get(str(pendiente.get("fixture_id")))
        if not resultado:
            sin_resolver += 1
            continue

        estado = evaluar_pick(
            pendiente.get("mercado", ""),
            pendiente.get("seleccion", ""),
            resultado.get("home_goals"),
            resultado.get("away_goals"),
        )
        if estado is None:
            sin_resolver += 1
            continue

        marcador = f"{resultado['home_goals']}-{resultado['away_goals']}"
        if update_prediction(pendiente["id"], estado, marcador, database_url=db_url):
            pendiente["estado"] = estado
            pendiente["resultado_real"] = marcador
            evaluadas.append(pendiente)
        else:
            sin_resolver += 1

    stats_global = get_stats(database_url=db_url)
    mensaje = build_audit_message(evaluadas, sin_resolver, stats_global, hoy.strftime("%Y-%m-%d"))

    if debug:
        print(mensaje)
        return

    if not tg_token or not targets:
        log.error("Faltan TELEGRAM_BOT_TOKEN o chats de destino para enviar la auditoría.")
        return

    for target in targets:
        ok = send_telegram(tg_token, target, mensaje)
        log.info("Auditoría enviada a %s: %s", target, "OK" if ok else "FALLÓ")
