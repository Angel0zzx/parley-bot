"""
VIP subscription management: activation, expiry revocation and Telegram admin commands.
"""

import html
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

from parley.config import (
    DATABASE_URL,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_VIP_CHAT_ID,
)
from parley.db import repository

log = logging.getLogger("parley.subs")

API_URL = "https://api.telegram.org/bot{token}/{method}"


def _now() -> datetime:
    """Current UTC time as a naive datetime (matches PostgreSQL TIMESTAMP)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize_expiry(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if isinstance(value, datetime) and value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _telegram_json(token: str, method: str, payload: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    if not token:
        log.warning("TELEGRAM_BOT_TOKEN no configurado; no se puede llamar a %s.", method)
        return None
    try:
        response = requests.post(
            API_URL.format(token=token, method=method),
            json=payload or {},
            timeout=20,
        )
    except requests.RequestException as exc:
        log.warning("Telegram %s no respondió: %s", method, type(exc).__name__)
        return None
    if not response.ok:
        log.warning("Telegram %s error %s: %s", method, response.status_code, response.text[:200])
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _telegram_call(token: str, method: str, payload: Optional[Dict[str, Any]] = None) -> bool:
    data = _telegram_json(token, method, payload)
    return bool(data and data.get("ok"))


def _create_invite_link(token: str, vip_chat_id: str) -> Optional[str]:
    data = _telegram_json(
        token,
        "createChatInviteLink",
        {"chat_id": vip_chat_id, "member_limit": 1},
    )
    if not data:
        return None
    return (data.get("result") or {}).get("invite_link")


def _get_updates(token: str, offset: Optional[int] = None, timeout: int = 0) -> List[Dict[str, Any]]:
    payload: Dict[str, Any] = {"timeout": timeout, "allowed_updates": ["message"]}
    if offset is not None:
        payload["offset"] = offset
    data = _telegram_json(token, "getUpdates", payload)
    return (data or {}).get("result") or []


def _send_message(token: str, chat_id: Any, text: str) -> bool:
    return _telegram_call(
        token,
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
    )


def activate_vip(
    user_id: Any,
    days: int = 30,
    username: Optional[str] = None,
    database_url: Optional[str] = None,
    telegram_token: Optional[str] = None,
    vip_chat_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Activate or renew a VIP subscription and create a one-use invite link."""
    uid = int(user_id)
    days = int(days)
    if days <= 0:
        raise ValueError("days debe ser mayor que 0")

    db_url = database_url if database_url is not None else DATABASE_URL
    token = telegram_token if telegram_token is not None else TELEGRAM_BOT_TOKEN
    vip = vip_chat_id if vip_chat_id is not None else TELEGRAM_VIP_CHAT_ID

    now = _now()
    current = repository.get_subscriber(uid, database_url=db_url)

    base = now
    if current and current.get("activo"):
        expiry = _normalize_expiry(current.get("expires_at"))
        if expiry and expiry > now:
            base = expiry

    expires_at = base + timedelta(days=days)
    plan = (current or {}).get("plan") or "mensual"
    saved = repository.upsert_subscriber(
        uid,
        expires_at,
        username=username,
        plan=plan,
        database_url=db_url,
    )

    invite_link = None
    if saved:
        invite_link = _create_invite_link(token, vip)
        if not invite_link:
            log.warning("No se pudo generar el enlace de invitación VIP para %s.", uid)

    return {
        "user_id": uid,
        "expires_at": expires_at,
        "invite_link": invite_link,
        "saved": saved,
    }


def revoke_expired_vips(
    database_url: Optional[str] = None,
    telegram_token: Optional[str] = None,
    vip_chat_id: Optional[str] = None,
) -> int:
    """Expel expired VIPs (ban + immediate unban) and mark them inactive."""
    db_url = database_url if database_url is not None else DATABASE_URL
    token = telegram_token if telegram_token is not None else TELEGRAM_BOT_TOKEN
    vip = vip_chat_id if vip_chat_id is not None else TELEGRAM_VIP_CHAT_ID

    expired = repository.get_expired_vips(database_url=db_url)
    if not expired:
        return 0
    if not token or not vip:
        log.warning("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_VIP_CHAT_ID; no se expulsan vencidos.")
        return 0

    revoked = 0
    for subscriber in expired:
        uid = subscriber.get("telegram_user_id")
        _telegram_call(token, "banChatMember", {"chat_id": vip, "user_id": uid})
        _telegram_call(token, "unbanChatMember", {"chat_id": vip, "user_id": uid})
        if repository.mark_subscriber_inactive(uid, database_url=db_url):
            revoked += 1
    return revoked


def _reply_usage(token: str, chat_id: Any) -> None:
    _send_message(
        token,
        chat_id,
        "Uso: <code>/vip &lt;telegram_user_id&gt; [dias]</code>\n"
        "Ejemplo: <code>/vip 123456789 30</code>",
    )


def process_admin_commands(
    database_url: Optional[str] = None,
    telegram_token: Optional[str] = None,
    admin_chat_id: Optional[str] = None,
    vip_chat_id: Optional[str] = None,
    offset: Optional[int] = None,
    timeout: int = 0,
    confirm: bool = True,
) -> Dict[str, Any]:
    """Process pending /vip and /estado commands from the admin chat only."""
    db_url = database_url if database_url is not None else DATABASE_URL
    token = telegram_token if telegram_token is not None else TELEGRAM_BOT_TOKEN
    admin = str(admin_chat_id if admin_chat_id is not None else TELEGRAM_CHAT_ID).strip()
    vip = vip_chat_id if vip_chat_id is not None else TELEGRAM_VIP_CHAT_ID

    if not token or not admin:
        log.warning("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID; no se procesan comandos.")
        return {"processed": 0, "last_update_id": None}

    updates = _get_updates(token, offset=offset, timeout=timeout)
    processed = 0
    last_update_id: Optional[int] = None

    for update in updates:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            last_update_id = update_id if last_update_id is None else max(last_update_id, update_id)

        message = update.get("message") or {}
        sender_id = (message.get("from") or {}).get("id")
        if sender_id is None or str(sender_id) != str(admin):
            continue

        chat_id = (message.get("chat") or {}).get("id")
        text = (message.get("text") or "").strip()
        if not text.startswith("/"):
            continue

        parts = text.split()
        command = parts[0].split("@")[0].lower()

        if command == "/vip":
            if len(parts) < 2:
                _reply_usage(token, chat_id)
                processed += 1
                continue
            try:
                user_id = int(parts[1])
            except ValueError:
                _reply_usage(token, chat_id)
                processed += 1
                continue
            days = 30
            if len(parts) >= 3:
                try:
                    days = int(parts[2])
                except ValueError:
                    _reply_usage(token, chat_id)
                    processed += 1
                    continue
            if days <= 0:
                _reply_usage(token, chat_id)
                processed += 1
                continue

            try:
                result = activate_vip(
                    user_id,
                    days=days,
                    database_url=db_url,
                    telegram_token=token,
                    vip_chat_id=vip,
                )
            except Exception as exc:
                log.error("Error activando VIP %s: %s", user_id, type(exc).__name__)
                _send_message(token, chat_id, "⚠️ No se pudo activar el VIP.")
                processed += 1
                continue
            if not result["saved"]:
                respuesta = "⚠️ No se pudo guardar el suscriptor. Revisa DATABASE_URL."
            else:
                vence = result["expires_at"].strftime("%Y-%m-%d %H:%M UTC")
                respuesta = (
                    f"✅ VIP activado para <code>{result['user_id']}</code>\n"
                    f"📅 Vence: <b>{vence}</b>"
                )
                if result["invite_link"]:
                    respuesta += f"\n🔗 Enlace de un solo uso:\n{html.escape(result['invite_link'])}"
                else:
                    respuesta += "\n⚠️ No se pudo generar el enlace de invitación."
            _send_message(token, chat_id, respuesta)
            processed += 1

        elif command == "/estado":
            activos = repository.count_active_vips(database_url=db_url)
            stats = repository.get_stats(database_url=db_url)
            respuesta = (
                f"👥 Suscriptores VIP activos: <b>{activos}</b>\n"
                f"📊 Resueltas: <b>{stats['total']}</b> "
                f"(✅ {stats['ganadas']} · ❌ {stats['perdidas']} · ⚪ {stats['nulas']})\n"
                f"🎯 Acierto: <b>{stats['acierto_pct']:.1f}%</b>\n"
                f"💵 ROI: <b>{stats['roi_pct']:+.1f}%</b>"
            )
            _send_message(token, chat_id, respuesta)
            processed += 1

    if confirm and last_update_id is not None:
        _get_updates(token, offset=last_update_id + 1, timeout=0)

    return {"processed": processed, "last_update_id": last_update_id}


def admin_listen(interval: int = 3, **kwargs: Any) -> None:
    """Light polling loop for admin commands."""
    offset: Optional[int] = kwargs.pop("offset", None)
    while True:
        try:
            result = process_admin_commands(offset=offset, confirm=False, **kwargs)
            if result.get("last_update_id") is not None:
                offset = result["last_update_id"] + 1
        except Exception as exc:
            log.error("Error procesando comandos admin: %s", type(exc).__name__)
        time.sleep(interval)
