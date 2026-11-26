"""
Telegram notification sender module.
"""

import html
import logging
import requests
from typing import List, Dict, Any
from zoneinfo import ZoneInfo
from parley.models.strategy import prob_conjunta, cuota_conjunta

log = logging.getLogger("parley.telegram")


def send_telegram(token: str, chat_id: str, text: str) -> bool:
    """Send text message to Telegram with chunking if text is too long."""
    if not token or not chat_id:
        log.error("Telegram token o chat_id no configurados.")
        return False

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
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": chunk.strip(),
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=30,
            )
        except requests.RequestException as exc:
            log.error("Telegram no respondió: %s", type(exc).__name__)
            return False
        if not r.ok:
            log.error("Telegram error %s: %s", r.status_code, r.text)
            return False
    return True


def build_mensaje(nivel: str, parley: List[Dict[str, Any]], fecha_objetivo: str, fecha_str: str, tz: ZoneInfo, titulo_prefijo: str = "PARLEY DIARIO") -> str:
    """Build HTML message for Telegram corresponding to a parley risk level."""
    titulos = {
        "seguro": f"🟢 <b>PARLEY SEGURO ({titulo_prefijo})</b>",
        "medio": f"🟡 <b>PARLEY MEDIO ({titulo_prefijo})</b>",
        "arriesgado": f"🔴 <b>PARLEY ARRIESGADO ({titulo_prefijo})</b>",
    }
    lines = [
        f"🎯 <b>{titulo_prefijo} — {fecha_str}</b>",
        f"📅 Fecha: <b>{fecha_objetivo}</b>",
        titulos.get(nivel, "<b>PARLEY</b>"),
        f"Selecciones: <b>{len(parley)}</b>\n",
    ]
    if not parley:
        lines.append("⚠️ Sin picks suficientes para este nivel.")
        return "\n".join(lines)

    for i, p in enumerate(parley, 1):
        hora = p["kickoff"].astimezone(tz).strftime("%H:%M") if p.get("kickoff") else "--:--"
        bloque = (
            f"<b>{i}. {html.escape(p['partido'])}</b>\n"
            f"   🏆 {html.escape(p['liga'])} · 🕒 {hora}\n"
            f"   🎯 {html.escape(p['seleccion'])} ({html.escape(p['mercado'])})\n"
            f"   📈 Prob: <b>{p['prob']:.1f}%</b> · Cuota justa: {p['cuota_justa']:.2f}\n"
        )
        if p.get("cuota_real"):
            label = "Cuota implícita" if p.get("derivada") else "Cuota"
            casa = html.escape(str(p.get("casa") or "?"))
            ev_txt = f" · EV: {p['ev'] * 100:+.1f}%" if p.get("ev") is not None else ""
            bloque += f"   💰 {label}: {p['cuota_real']:.2f} ({casa}){ev_txt}\n"
        lines.append(bloque)

    lines.append(
        f"\n📊 <b>RESUMEN</b>\n"
        f"Probabilidad conjunta: <b>{prob_conjunta(parley):.1f}%</b>\n"
        f"Cuota justa combinada: <b>{cuota_conjunta(parley):.2f}</b>"
    )
    lines.append("⚠️ Modelo estadístico. Sin garantías. Stake plano y responsable.")
    return "\n".join(lines)
