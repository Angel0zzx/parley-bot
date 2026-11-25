"""
Unified CLI interface for Parley bot.
"""

import argparse
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from parley.config import (
    FOOTBALL_DATA_KEY,
    BZZOIRO_API_KEY,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TIMEZONE,
)
from parley.providers.football_data import FootballDataProvider
from parley.providers.bzzoiro import BzzoiroProvider
from parley.models.strategy import generar_picks, armar_parleys
from parley.notifiers.telegram import send_telegram, build_mensaje

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
            print(f"    {p['seleccion']:22s} ({p['mercado']:6s}) prob={p['prob']:.1f}% "
                  f"cuota={p['cuota_justa']:.2f} @ {hora}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Parley bot unificado — football-data.org / Bzzoiro")
    parser.add_argument("--provider", type=str, choices=["fd", "bzzoiro"], default="fd", help="Proveedor de datos (fd o bzzoiro)")
    parser.add_argument("--fecha", type=str, default=None, help="YYYY-MM-DD (def. hoy)")
    parser.add_argument("--debug", action="store_true", help="Solo imprime, sin enviar")
    parser.add_argument("--incluir-pasados", action="store_true", help="Incluye partidos que ya empezaron hoy")
    args = parser.parse_args()

    if args.provider == "fd":
        if not FOOTBALL_DATA_KEY:
            sys.exit("Falta FOOTBALL_DATA_KEY en el .env")
        provider = FootballDataProvider(FOOTBALL_DATA_KEY)
        titulo_prefijo = "FOOTBALL-DATA"
    else:
        if not BZZOIRO_API_KEY:
            sys.exit("Falta BZZOIRO_API_KEY en el .env")
        provider = BzzoiroProvider(BZZOIRO_API_KEY)
        titulo_prefijo = "SUDAMÉRICA"

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

    log.info("Fecha objetivo: %s [%s]", fecha_obj_str, args.provider)

    cache = {"form": {}}
    solo_futuros = not args.incluir_pasados
    partidos = provider.get_matches(fecha_obj_str, tz, solo_futuros=solo_futuros)

    if not partidos:
        msg = (f"🎯 <b>PARLEY {titulo_prefijo} — {fecha_str}</b>\n"
               f"📅 Fecha: <b>{fecha_obj_str}</b>\n\n"
               f"⚠️ No hay partidos programados para esa fecha.")
        if not args.debug:
            send_telegram(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, msg)
        else:
            print(msg)
        return

    todos_picks = []
    for partido in partidos:
        hf = provider.get_team_form(partido.get("home_id"), cache)
        af = provider.get_team_form(partido.get("away_id"), cache)
        picks = generar_picks(partido, hf, af)
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
        msg = build_mensaje(nivel, parleys[nivel], fecha_obj_str, fecha_str, tz, titulo_prefijo)
        ok = send_telegram(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, msg)
        log.info("Enviado '%s' (%d selecciones): %s", nivel, len(parleys[nivel]), "OK" if ok else "FALLÓ")


if __name__ == "__main__":
    main()
