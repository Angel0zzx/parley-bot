"""
Unified CLI interface for Parley bot with interactive menu support, persistent cache, and setup wizard.
"""

import argparse
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from parley.config import (
    ENV_PATH,
    FOOTBALL_DATA_KEY,
    BZZOIRO_API_KEY,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TIMEZONE,
    ODDS_API_KEY,
)
from parley.providers.football_data import FootballDataProvider
from parley.providers.bzzoiro import BzzoiroProvider
from parley.providers.odds_api import OddsApiClient
from parley.models.strategy import generar_picks, armar_parleys
from parley.notifiers.telegram import send_telegram, build_mensaje
from parley.db.repository import save_predictions
from parley.utils.cache import load_cache
from parley.utils.setup_wizard import run_setup_wizard

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("parley.cli")


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
            hora = p["kickoff"].astimezone(tz).strftime("%H:%M") if p.get("kickoff") else "--:--"
            extra = ""
            if p.get("cuota_real"):
                label = "Cuota implícita" if p.get("derivada") else "Cuota"
                extra = f" | 💰 {label}: {p['cuota_real']:.2f} ({p.get('casa') or '?'})"
                if p.get("ev") is not None:
                    extra += f" · EV: {p['ev'] * 100:+.1f}%"
            print(f"    {p['seleccion']:22s} ({p['mercado']:6s}) prob={p['prob']:.1f}% "
                  f"cuota={p['cuota_justa']:.2f} @ {hora}{extra}")
        print()


def run_provider(provider_code, fecha_obj_str, fecha_str, tz, debug, incluir_pasados, min_ev=None, sin_cuotas=False):
    # Recargar variables de entorno por si el wizard acaba de actualizar el .env
    fd_key = os.getenv("FOOTBALL_DATA_KEY", FOOTBALL_DATA_KEY)
    bzz_key = os.getenv("BZZOIRO_API_KEY", BZZOIRO_API_KEY)
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN", TELEGRAM_BOT_TOKEN)
    tg_chat_id = os.getenv("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID)

    if provider_code == "fd":
        if not fd_key:
            log.error("Falta FOOTBALL_DATA_KEY en el .env")
            return
        provider = FootballDataProvider(fd_key)
        titulo_prefijo = "FOOTBALL-DATA"
    else:
        if not bzz_key:
            log.error("Falta BZZOIRO_API_KEY en el .env")
            return
        provider = BzzoiroProvider(bzz_key)
        titulo_prefijo = "SUDAMÉRICA"

    if not debug and (not tg_token or not tg_chat_id):
        log.error("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en el .env")
        return

    log.info("Ejecutando proveedor: %s para fecha %s", titulo_prefijo, fecha_obj_str)
    solo_futuros = not incluir_pasados
    partidos = provider.get_matches(fecha_obj_str, tz, solo_futuros=solo_futuros)

    if not partidos:
        msg = (f"🎯 <b>PARLEY {titulo_prefijo} — {fecha_str}</b>\n"
               f"📅 Fecha: <b>{fecha_obj_str}</b>\n\n"
               f"⚠️ No hay partidos programados para esa fecha.")
        if not debug:
            send_telegram(tg_token, tg_chat_id, msg)
        else:
            print(msg)
        return

    cache = load_cache()
    odds_map = {}
    odds_key = os.getenv("ODDS_API_KEY", ODDS_API_KEY)
    if not sin_cuotas and odds_key:
        try:
            odds_map = OddsApiClient(api_key=odds_key).get_odds_for_matches(partidos, cache)
            log.info("Cuotas reales obtenidas para %d partidos", len(odds_map))
        except Exception as exc:
            log.warning("No se pudieron obtener cuotas reales: %s", type(exc).__name__)
    todos_picks = []
    for partido in partidos:
        hf = provider.get_team_form(partido.get("home_id"), cache)
        af = provider.get_team_form(partido.get("away_id"), cache)
        picks = generar_picks(partido, hf, af, odds=odds_map.get(partido.get("id")), min_ev=min_ev)
        todos_picks.extend(picks)
        log.info("  %s vs %s → %d picks", partido["home"], partido["away"], len(picks))

    log.info("Picks generados (%s): %d", titulo_prefijo, len(todos_picks))
    if not debug and todos_picks:
        guardadas = save_predictions(todos_picks, fecha_obj_str)
        log.info("Predicciones persistidas: %d", guardadas)
    parleys = armar_parleys(todos_picks)

    if debug:
        debug_dump(todos_picks, tz)
        print(f"\n--- PARLEYS ({titulo_prefijo}) ---")
        for nivel, parley in parleys.items():
            print(f"\n{nivel.upper()} ({len(parley)} selecciones):")
            for p in parley:
                print(f"  {p['seleccion']} ({p['partido']}) prob={p['prob']:.1f}%")
        return

    for nivel in ["seguro", "medio", "arriesgado"]:
        msg = build_mensaje(nivel, parleys[nivel], fecha_obj_str, fecha_str, tz, titulo_prefijo)
        ok = send_telegram(tg_token, tg_chat_id, msg)
        log.info("Enviado '%s' (%d selecciones): %s", nivel, len(parleys[nivel]), "OK" if ok else "FALLÓ")


import os

def main():
    parser = argparse.ArgumentParser(description="Parley bot unificado — football-data.org / Bzzoiro")
    parser.add_argument("--provider", type=str, choices=["fd", "bzzoiro", "ambos"], default=None, help="Proveedor: fd, bzzoiro o ambos")
    parser.add_argument("--fecha", type=str, default=None, help="YYYY-MM-DD (def. hoy)")
    parser.add_argument("--debug", action="store_true", help="Solo imprime, sin enviar")
    parser.add_argument("--incluir-pasados", action="store_true", help="Incluye partidos que ya empezaron hoy")
    parser.add_argument("--min-ev", type=float, default=None, help="EV mínimo para conservar picks con cuota real (def. 0.0)")
    parser.add_argument("--sin-cuotas", action="store_true", help="Ignora The Odds API y usa solo el modelo")
    parser.add_argument("--audit", action="store_true", help="Audita picks pendientes y envía el resumen nocturno")
    args = parser.parse_args()

    # Ejecutar el asistente solo si faltan ambas credenciales y la terminal es interactiva
    current_fd = os.getenv("FOOTBALL_DATA_KEY", FOOTBALL_DATA_KEY)
    current_bzz = os.getenv("BZZOIRO_API_KEY", BZZOIRO_API_KEY)
    if not current_fd and not current_bzz and sys.stdin.isatty():
        run_setup_wizard(ENV_PATH)

    if args.audit:
        from parley.audit import run_audit
        tz = ZoneInfo(os.getenv("TZ_LOCAL", TIMEZONE))
        run_audit(
            fd_key=os.getenv("FOOTBALL_DATA_KEY", FOOTBALL_DATA_KEY),
            tg_token=os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN", TELEGRAM_BOT_TOKEN),
            tg_chat_id=os.getenv("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID),
            tz=tz,
            debug=args.debug,
        )
        if getattr(sys, "frozen", False):
            input("\nProceso finalizado. Presiona Enter para salir...")
        return

    provider_arg = args.provider
    # Interactive menu if no arguments passed (e.g. double click on Windows .exe)
    if provider_arg is None and len(sys.argv) == 1:
        while True:
            print("\n==============================================")
            print("          BOT DE PARLEY - MENÚ INTERACTIVO    ")
            print("==============================================")
            print("Selecciona una opción:")
            print("  [1] Football-Data.org (Ligas Europeas + Champions)")
            print("  [2] Bzzoiro Sports Data (Liga Argentina / Sudamérica)")
            print("  [3] Ambos proveedores")
            print("  [4] Reconfigurar credenciales (.env)")
            opcion = input("Elige una opción [1-4] (por defecto 1): ").strip()
            if opcion == "4":
                run_setup_wizard(ENV_PATH)
                continue
            elif opcion == "2":
                provider_arg = "bzzoiro"
            elif opcion == "3":
                provider_arg = "ambos"
            else:
                provider_arg = "fd"
            break

        debug_op = input("¿Modo debug (solo imprimir en pantalla)? [s/N]: ").strip().lower()
        if debug_op == "s":
            args.debug = True

    if provider_arg is None:
        provider_arg = "fd"

    tz = ZoneInfo(os.getenv("TZ_LOCAL", TIMEZONE))
    ahora = datetime.now(tz)
    fecha_obj_str = args.fecha or ahora.date().strftime("%Y-%m-%d")
    fecha_str = ahora.strftime("%Y-%m-%d %H:%M")

    if provider_arg == "ambos":
        run_provider("fd", fecha_obj_str, fecha_str, tz, args.debug, args.incluir_pasados, min_ev=args.min_ev, sin_cuotas=args.sin_cuotas)
        run_provider("bzzoiro", fecha_obj_str, fecha_str, tz, args.debug, args.incluir_pasados, min_ev=args.min_ev, sin_cuotas=args.sin_cuotas)
    else:
        run_provider(provider_arg, fecha_obj_str, fecha_str, tz, args.debug, args.incluir_pasados, min_ev=args.min_ev, sin_cuotas=args.sin_cuotas)

    if getattr(sys, 'frozen', False):
        input("\nProceso finalizado. Presiona Enter para salir...")


if __name__ == "__main__":
    main()
