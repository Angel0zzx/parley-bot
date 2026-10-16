#!/usr/bin/env python3
"""
parley_argentina.py — Parley diario con Bzzoiro Sports Data + modelo Poisson.
Cubre la Liga Profesional Argentina y otras ligas de Sudamérica.

Uso:
    python parley_argentina.py                    # analiza HOY
    python parley_argentina.py --fecha 2026-10-17 # analiza ese día
    python parley_argentina.py --debug            # solo imprime, sin enviar
    python parley_argentina.py --incluir-pasados  # incluye en vivo/terminados
"""

import argparse
import html
import logging
import math
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BZZOIRO_API_KEY = os.getenv("BZZOIRO_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TIMEZONE = os.getenv("TZ_LOCAL", "America/Guayaquil")

# --- Ligas a cubrir (IDs de Bzzoiro) -------------------------------------
LIGAS_SUDAMERICA = {
    85: "Liga Profesional Argentina",
    # 268: "Copa Libertadores",
    # 269: "Copa Sudamericana",
    # 1: "Brasileirao",
}

# --- Modelo ---------------------------------------------------------------
RECENT_MATCHES = 10
MIN_MATCHES_REQUIRED = 3
LINEAS_GOLES = [1.5, 2.5, 3.5]

# --- Niveles de riesgo ----------------------------------------------------
RIESGO_SEGURO_MIN = 72.0
RIESGO_MEDIO_MIN = 62.0
RIESGO_BAJO_MIN = 52.0
PROB_MAX = 95.0

PARLEY_MAX = 3
PAUSA_API = 0.2

BASE_URL = "https://sports.bzzoiro.com/api/v2"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("parley_arg")

_last_call = 0.0

# Estados que NO se juegan (excluir siempre)
STATUS_EXCLUIDOS = {"cancelled", "postponed", "unresolved", "abandoned"}


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
def api_get(path, params=None, retries=3):
    global _last_call
    wait = PAUSA_API - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)

    url = f"{BASE_URL}{path}"
    headers = {"Authorization": f"Token {BZZOIRO_API_KEY}"}

    for intento in range(1, retries + 1):
        try:
            _last_call = time.time()
            r = requests.get(url, headers=headers, params=params, timeout=30)
            if r.status_code == 429:
                log.warning("Rate limit. Esperando 5s...")
                time.sleep(5)
                continue
            if r.status_code == 401:
                log.error("API key de Bzzoiro inválida (401).")
                return None
            r.raise_for_status()
            return r.json()
        except requests.RequestException as exc:
            log.warning("Petición falló (%d/%d): %s", intento, retries, type(exc).__name__)
            time.sleep(2 * intento)
    return None


# --------------------------------------------------------------------------
# POISSON
# --------------------------------------------------------------------------
def poisson_pmf(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def prob_over(lam_total, linea):
    umbral = int(linea)
    acum = sum(poisson_pmf(k, lam_total) for k in range(umbral + 1))
    return max(0.0, min(1.0, 1.0 - acum))


def prob_btts(lam_home, lam_away):
    p_home_0 = poisson_pmf(0, lam_home)
    p_away_0 = poisson_pmf(0, lam_away)
    return (1 - p_home_0) * (1 - p_away_0)


def expected_goals(home_form, away_form):
    lam_h = (home_form["gf"] + away_form["ga"]) / 2
    lam_a = (away_form["gf"] + home_form["ga"]) / 2
    lam_h = min(max(lam_h, 0.3), 4.0)
    lam_a = min(max(lam_a, 0.3), 4.0)
    return lam_h, lam_a


# --------------------------------------------------------------------------
# FORMA DE EQUIPOS
# --------------------------------------------------------------------------
def get_team_form(team_id, cache):
    key = str(team_id)
    if key in cache["form"]:
        return cache["form"][key]

    hoy = datetime.now(timezone.utc).date()
    date_from = (hoy - timedelta(days=120)).strftime("%Y-%m-%d")
    date_to = hoy.strftime("%Y-%m-%d")

    data = api_get("/events/", params={
        "team": team_id,
        "date_from": date_from,
        "date_to": date_to,
    })
    if not data:
        cache["form"][key] = None
        return None

    partidos = data.get("results", [])
    terminados = []
    for m in partidos:
        if m.get("status") != "finished":
            continue
        hs = m.get("home_score")
        as_ = m.get("away_score")
        if hs is None or as_ is None:
            continue
        terminados.append(m)

    if len(terminados) < MIN_MATCHES_REQUIRED:
        cache["form"][key] = None
        return None

    terminados.sort(key=lambda m: m.get("event_date", ""), reverse=True)
    terminados = terminados[:RECENT_MATCHES]

    gf, ga = [], []
    for m in terminados:
        hs = m["home_score"]
        as_ = m["away_score"]
        es_local = m.get("home_team_obj", {}).get("id") == team_id
        gf.append(hs if es_local else as_)
        ga.append(as_ if es_local else hs)

    form = {
        "gf": sum(gf) / len(gf),
        "ga": sum(ga) / len(ga),
        "n": len(gf),
    }
    cache["form"][key] = form
    return form


# --------------------------------------------------------------------------
# PARTIDOS POR FECHA
# --------------------------------------------------------------------------
def get_partidos_fecha(fecha_str, tz, solo_futuros=True):
    f_obj = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    date_from = (f_obj - timedelta(days=1)).strftime("%Y-%m-%d")
    date_to = (f_obj + timedelta(days=1)).strftime("%Y-%m-%d")

    ahora_utc = datetime.now(timezone.utc)
    partidos = []

    for league_id, nombre in LIGAS_SUDAMERICA.items():
        data = api_get("/events/", params={
            "league": league_id,
            "date_from": date_from,
            "date_to": date_to,
        })
        if not data:
            continue

        for m in data.get("results", []):
            status = (m.get("status") or "").lower()

            # Excluir solo los que no se juegan
            if status in STATUS_EXCLUIDOS:
                continue

            event_date = m.get("event_date")
            if not event_date:
                continue
            try:
                kickoff = datetime.fromisoformat(event_date.replace("Z", "+00:00"))
            except ValueError:
                continue

            # Filtro por fecha en hora LOCAL
            kickoff_local = kickoff.astimezone(tz)
            if kickoff_local.strftime("%Y-%m-%d") != fecha_str:
                continue

            # Filtro de partidos ya iniciados
            if solo_futuros and kickoff <= ahora_utc:
                continue

            partidos.append({
                "id": m.get("id"),
                "kickoff": kickoff,
                "liga": nombre,
                "home_id": m.get("home_team_obj", {}).get("id"),
                "home": m.get("home_team", "?"),
                "away_id": m.get("away_team_obj", {}).get("id"),
                "away": m.get("away_team", "?"),
            })

    log.info("Partidos en %s (hora local %s): %d", fecha_str, tz.key, len(partidos))
    return partidos


# --------------------------------------------------------------------------
# GENERAR PICKS
# --------------------------------------------------------------------------
def generar_picks(partido, cache):
    hf = get_team_form(partido["home_id"], cache)
    af = get_team_form(partido["away_id"], cache)
    if not hf or not af:
        return []

    lam_h, lam_a = expected_goals(hf, af)
    lam_total = lam_h + lam_a

    picks = []

    for linea in LINEAS_GOLES:
        p_over = prob_over(lam_total, linea)
        p_under = 1 - p_over

        if RIESGO_BAJO_MIN <= p_over * 100 <= PROB_MAX:
            picks.append({
                "partido": f"{partido['home']} vs {partido['away']}",
                "liga": partido["liga"],
                "seleccion": f"Over {linea}",
                "mercado": "Goles",
                "prob": p_over * 100,
                "cuota_justa": 1 / p_over if p_over > 0 else 0,
                "kickoff": partido["kickoff"],
            })

        if RIESGO_BAJO_MIN <= p_under * 100 <= PROB_MAX:
            picks.append({
                "partido": f"{partido['home']} vs {partido['away']}",
                "liga": partido["liga"],
                "seleccion": f"Under {linea}",
                "mercado": "Goles",
                "prob": p_under * 100,
                "cuota_justa": 1 / p_under if p_under > 0 else 0,
                "kickoff": partido["kickoff"],
            })

    p_btts = prob_btts(lam_h, lam_a)
    if RIESGO_BAJO_MIN <= p_btts * 100 <= PROB_MAX:
        picks.append({
            "partido": f"{partido['home']} vs {partido['away']}",
            "liga": partido["liga"],
            "seleccion": "Ambos anotan: SÍ",
            "mercado": "BTTS",
            "prob": p_btts * 100,
            "cuota_justa": 1 / p_btts if p_btts > 0 else 0,
            "kickoff": partido["kickoff"],
        })

    return picks


# --------------------------------------------------------------------------
# RIESGO + PARLEYS
# --------------------------------------------------------------------------
def clasificar_riesgo(prob):
    if prob >= RIESGO_SEGURO_MIN: return "seguro"
    if prob >= RIESGO_MEDIO_MIN: return "medio"
    if prob >= RIESGO_BAJO_MIN: return "arriesgado"
    return None


def tomar_mejores(candidatos, max_sel=PARLEY_MAX):
    ordenados = sorted(candidatos, key=lambda x: -x["prob"])
    seleccion, partidos = [], set()
    for p in ordenados:
        if p["partido"] in partidos:
            continue
        seleccion.append(p)
        partidos.add(p["partido"])
        if len(seleccion) >= max_sel:
            break
    return seleccion


def armar_parleys(picks):
    por_riesgo = {"seguro": [], "medio": [], "arriesgado": []}
    for p in picks:
        nivel = clasificar_riesgo(p["prob"])
        if nivel:
            p["riesgo"] = nivel
            por_riesgo[nivel].append(p)
    return {nivel: tomar_mejores(lista) for nivel, lista in por_riesgo.items()}


def prob_conjunta(parley):
    p = 1.0
    for x in parley:
        p *= x["prob"] / 100.0
    return p * 100


def cuota_conjunta(parley):
    c = 1.0
    for x in parley:
        if x["cuota_justa"] > 0:
            c *= x["cuota_justa"]
    return c


# --------------------------------------------------------------------------
# TELEGRAM
# --------------------------------------------------------------------------
def send_telegram(text):
    chunks, current = [], ""
    for block in text.split("\n\n"):
        if len(current) + len(block) + 2 > 3800:
            chunks.append(current)
            current = ""
        current += block + "\n\n"
    chunks.append(current)
    for chunk in chunks:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": chunk.strip(),
                      "parse_mode": "HTML", "disable_web_page_preview": True},
                timeout=30,
            )
        except requests.RequestException as exc:
            log.error("Telegram no respondió: %s", type(exc).__name__)
            return False
        if not r.ok:
            log.error("Telegram error %s: %s", r.status_code, r.text)
            return False
    return True


def build_mensaje(nivel, parley, fecha_objetivo, fecha_str, tz):
    titulos = {
        "seguro": "🟢 <b>PARLEY SEGURO (SUDAMÉRICA)</b>",
        "medio": "🟡 <b>PARLEY MEDIO (SUDAMÉRICA)</b>",
        "arriesgado": "🔴 <b>PARLEY ARRIESGADO (SUDAMÉRICA)</b>",
    }
    lines = [
        f"🎯 <b>PARLEY SUDAMÉRICA — {fecha_str}</b>",
        f"📅 Fecha: <b>{fecha_objetivo}</b>",
        titulos[nivel],
        f"Selecciones: <b>{len(parley)}</b>\n",
    ]
    if not parley:
        lines.append("⚠️ Sin picks suficientes para este nivel.")
        return "\n".join(lines)

    for i, p in enumerate(parley, 1):
        hora = p["kickoff"].astimezone(tz).strftime("%H:%M")
        lines.append(
            f"<b>{i}. {html.escape(p['partido'])}</b>\n"
            f"   🏆 {html.escape(p['liga'])} · 🕒 {hora}\n"
            f"   🎯 {html.escape(p['seleccion'])} ({html.escape(p['mercado'])})\n"
            f"   📈 Prob: <b>{p['prob']:.1f}%</b> · Cuota justa: {p['cuota_justa']:.2f}\n"
        )

    lines.append(
        f"\n📊 <b>RESUMEN</b>\n"
        f"Probabilidad conjunta: <b>{prob_conjunta(parley):.1f}%</b>\n"
        f"Cuota justa combinada: <b>{cuota_conjunta(parley):.2f}</b>"
    )
    lines.append("⚠️ Modelo estadístico. Sin garantías. Stake plano y responsable.")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# DEBUG
# --------------------------------------------------------------------------
def debug_dump(picks, tz):
    if not picks:
        print("(No hay picks para esa fecha)")
        return
    por_partido = {}
    for p in picks:
        por_partido.setdefault(p["partido"], []).append(p)
    print(f"\n=== {len(picks)} picks en {len(por_partido)} partidos ===\n")
    for partido, lista in sorted(por_partido.items()):
        print(f"▶ {partido}  ({lista[0]['liga']})")
        for p in sorted(lista, key=lambda x: -x["prob"]):
            hora = p["kickoff"].astimezone(tz).strftime("%H:%M")
            print(f"    {p['seleccion']:22s} ({p['mercado']:6s}) prob={p['prob']:.1f}% "
                  f"cuota={p['cuota_justa']:.2f} @ {hora}")
        print()


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Parley Sudamérica — Bzzoiro")
    parser.add_argument("--fecha", type=str, default=None, help="YYYY-MM-DD (def. hoy)")
    parser.add_argument("--debug", action="store_true", help="Solo imprime, sin enviar")
    parser.add_argument("--incluir-pasados", action="store_true",
                        help="Incluye partidos que ya empezaron hoy")
    args = parser.parse_args()

    if not BZZOIRO_API_KEY:
        sys.exit("Falta BZZOIRO_API_KEY en el .env")
    if not args.debug and (not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID):
        sys.exit("Faltan TELEGRAM_BOT_TOKEN/TELEGRAM_TOKEN o TELEGRAM_CHAT_ID en el .env")

    tz = ZoneInfo(TIMEZONE)
    ahora = datetime.now(tz)

    if args.fecha:
        try:
            fecha_obj = datetime.strptime(args.fecha, "%Y-%m-%d").date()
        except ValueError:
            sys.exit(f"Fecha inválida: {args.fecha} (usa YYYY-MM-DD)")
    else:
        fecha_obj = ahora.date()

    fecha_obj_str = fecha_obj.strftime("%Y-%m-%d")
    fecha_str = ahora.strftime("%Y-%m-%d %H:%M")

    log.info("Fecha objetivo: %s", fecha_obj_str)

    cache = {"form": {}}

    solo_futuros = not args.incluir_pasados
    partidos = get_partidos_fecha(fecha_obj_str, tz, solo_futuros=solo_futuros)

    if not partidos:
        msg = (f"🎯 <b>PARLEY SUDAMÉRICA — {fecha_str}</b>\n"
               f"📅 Fecha: <b>{fecha_obj_str}</b>\n\n"
               f"⚠️ No hay partidos programados para esa fecha.")
        if not args.debug:
            send_telegram(msg)
        else:
            print(msg)
        return

    todos_picks = []
    for partido in partidos:
        picks = generar_picks(partido, cache)
        todos_picks.extend(picks)
        log.info("  %s vs %s → %d picks", partido["home"], partido["away"], len(picks))

    log.info("Picks generados: %d", len(todos_picks))

    parleys = armar_parleys(todos_picks)

    if args.debug:
        debug_dump(todos_picks, tz)
        print("\n--- PARLEYS ---")
        for nivel, parley in parleys.items():
            print(f"\n{nivel.upper()} ({len(parley)} selecciones):")
            for p in parley:
                print(f"  {p['seleccion']} ({p['partido']}) prob={p['prob']:.1f}%")
        return

    for nivel in ["seguro", "medio", "arriesgado"]:
        msg = build_mensaje(nivel, parleys[nivel], fecha_obj_str, fecha_str, tz)
        ok = send_telegram(msg)
        log.info("Enviado '%s' (%d selecciones): %s",
                 nivel, len(parleys[nivel]), "OK" if ok else "FALLÓ")


if __name__ == "__main__":
    main()