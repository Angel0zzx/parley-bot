"""
Tests for VIP subscriptions, admin command security and Free/VIP routing.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from parley import subscriptions as subs
from parley.db import repository
from parley.notifiers.telegram import (
    build_free_mensaje,
    get_audit_targets,
    get_morning_targets,
)


def _patch_upsert(monkeypatch, captured):
    def fake_upsert(uid, expires_at, username=None, plan="mensual", database_url=None):
        captured.update(
            uid=uid,
            expires_at=expires_at,
            username=username,
            plan=plan,
            database_url=database_url,
        )
        return True

    monkeypatch.setattr(repository, "upsert_subscriber", fake_upsert)


def test_activate_new_subscriber_adds_days_from_now(monkeypatch):
    fixed = datetime(2026, 11, 26, 12, 0, 0)
    captured = {}

    monkeypatch.setattr(subs, "_now", lambda: fixed)
    monkeypatch.setattr(repository, "get_subscriber", lambda *a, **k: None)
    _patch_upsert(monkeypatch, captured)
    monkeypatch.setattr(subs, "_create_invite_link", lambda token, vip: "https://t.me/+one")

    result = subs.activate_vip(
        123,
        days=30,
        username="alice",
        database_url="db",
        telegram_token="tok",
        vip_chat_id="-100vip",
    )

    assert result["saved"] is True
    assert result["expires_at"] == fixed + timedelta(days=30)
    assert result["invite_link"] == "https://t.me/+one"
    assert captured["uid"] == 123
    assert captured["username"] == "alice"


def test_activate_renewal_adds_days_to_current_expiry(monkeypatch):
    fixed = datetime(2026, 11, 26, 12, 0, 0)
    current_expiry = fixed + timedelta(days=10)
    captured = {}

    monkeypatch.setattr(subs, "_now", lambda: fixed)
    monkeypatch.setattr(
        repository,
        "get_subscriber",
        lambda *a, **k: {"activo": True, "expires_at": current_expiry, "plan": "mensual"},
    )
    _patch_upsert(monkeypatch, captured)
    monkeypatch.setattr(subs, "_create_invite_link", lambda token, vip: None)

    result = subs.activate_vip(123, days=30, database_url="db", telegram_token="tok", vip_chat_id="-100vip")

    assert result["expires_at"] == current_expiry + timedelta(days=30)


def test_activate_expired_subscriber_starts_from_now(monkeypatch):
    fixed = datetime(2026, 11, 26, 12, 0, 0)
    captured = {}

    monkeypatch.setattr(subs, "_now", lambda: fixed)
    monkeypatch.setattr(
        repository,
        "get_subscriber",
        lambda *a, **k: {"activo": True, "expires_at": fixed - timedelta(days=5), "plan": "mensual"},
    )
    _patch_upsert(monkeypatch, captured)
    monkeypatch.setattr(subs, "_create_invite_link", lambda token, vip: None)

    result = subs.activate_vip(123, days=30, database_url="db", telegram_token="tok", vip_chat_id="-100vip")

    assert result["expires_at"] == fixed + timedelta(days=30)


def test_activate_without_db_skips_invite(monkeypatch):
    invite_calls = []

    monkeypatch.setattr(repository, "get_subscriber", lambda *a, **k: None)
    monkeypatch.setattr(repository, "upsert_subscriber", lambda *a, **k: False)
    monkeypatch.setattr(subs, "_create_invite_link", lambda *a, **k: invite_calls.append(True))

    result = subs.activate_vip(1, database_url="", telegram_token="tok", vip_chat_id="-100vip")

    assert result["saved"] is False
    assert result["invite_link"] is None
    assert invite_calls == []


def test_revoke_expired_vips_ban_then_unban(monkeypatch):
    calls = []
    inactive = []

    monkeypatch.setattr(
        repository,
        "get_expired_vips",
        lambda database_url=None: [
            {"telegram_user_id": 11},
            {"telegram_user_id": 22},
        ],
    )

    def fake_call(token, method, payload=None):
        calls.append((method, payload))
        return True

    monkeypatch.setattr(subs, "_telegram_call", fake_call)
    monkeypatch.setattr(
        repository,
        "mark_subscriber_inactive",
        lambda uid, database_url=None: inactive.append(uid) or True,
    )

    revoked = subs.revoke_expired_vips(
        database_url="db",
        telegram_token="tok",
        vip_chat_id="-100vip",
    )

    assert revoked == 2
    assert [c[0] for c in calls] == [
        "banChatMember",
        "unbanChatMember",
        "banChatMember",
        "unbanChatMember",
    ]
    assert inactive == [11, 22]


def test_process_admin_commands_ignores_non_admin(monkeypatch):
    updates = [
        {
            "update_id": 1,
            "message": {
                "from": {"id": 999},
                "chat": {"id": 999},
                "text": "/vip 123 30",
            },
        }
    ]
    activated = []
    sent = []

    monkeypatch.setattr(subs, "_get_updates", lambda token, offset=None, timeout=0: updates)
    monkeypatch.setattr(subs, "activate_vip", lambda *a, **k: activated.append((a, k)))
    monkeypatch.setattr(subs, "_send_message", lambda *a, **k: sent.append((a, k)))

    result = subs.process_admin_commands(
        database_url="db",
        telegram_token="tok",
        admin_chat_id="111",
        vip_chat_id="-100vip",
        confirm=False,
    )

    assert result["processed"] == 0
    assert activated == []
    assert sent == []


def test_process_admin_commands_vip_for_admin(monkeypatch):
    updates = [
        {
            "update_id": 5,
            "message": {
                "from": {"id": 111},
                "chat": {"id": 111},
                "text": "/vip 123 15",
            },
        }
    ]
    activated = []
    sent = []

    monkeypatch.setattr(subs, "_get_updates", lambda token, offset=None, timeout=0: updates)

    def fake_activate(user_id, days=30, **kwargs):
        activated.append((user_id, days, kwargs))
        return {
            "saved": True,
            "user_id": user_id,
            "expires_at": datetime(2027, 1, 1, 0, 0, 0),
            "invite_link": "https://t.me/+invite",
        }

    monkeypatch.setattr(subs, "activate_vip", fake_activate)
    monkeypatch.setattr(subs, "_send_message", lambda token, chat_id, text: sent.append((chat_id, text)) or True)

    result = subs.process_admin_commands(
        database_url="db",
        telegram_token="tok",
        admin_chat_id="111",
        vip_chat_id="-100vip",
        confirm=False,
    )

    assert result["processed"] == 1
    assert activated[0][0] == 123
    assert activated[0][1] == 15
    assert sent[0][0] == 111
    assert "Vence" in sent[0][1]
    assert "https://t.me/+invite" in sent[0][1]


def test_process_admin_commands_rejects_non_positive_days(monkeypatch):
    updates = [
        {
            "update_id": 6,
            "message": {
                "from": {"id": 111},
                "chat": {"id": 111},
                "text": "/vip 123 0",
            },
        }
    ]
    activated = []
    sent = []

    monkeypatch.setattr(subs, "_get_updates", lambda token, offset=None, timeout=0: updates)
    monkeypatch.setattr(subs, "activate_vip", lambda *a, **k: activated.append((a, k)))
    monkeypatch.setattr(subs, "_send_message", lambda token, chat_id, text: sent.append((chat_id, text)) or True)

    result = subs.process_admin_commands(
        database_url="db",
        telegram_token="tok",
        admin_chat_id="111",
        vip_chat_id="-100vip",
        confirm=False,
    )

    assert result["processed"] == 1
    assert activated == []
    assert sent[0][0] == 111
    assert "Uso" in sent[0][1]


def test_process_admin_commands_estado(monkeypatch):
    updates = [
        {
            "update_id": 7,
            "message": {
                "from": {"id": 111},
                "chat": {"id": 111},
                "text": "/estado",
            },
        }
    ]
    sent = []

    monkeypatch.setattr(subs, "_get_updates", lambda token, offset=None, timeout=0: updates)
    monkeypatch.setattr(repository, "count_active_vips", lambda database_url=None: 4)
    monkeypatch.setattr(
        repository,
        "get_stats",
        lambda database_url=None: {
            "total": 10,
            "ganadas": 6,
            "perdidas": 4,
            "nulas": 1,
            "acierto_pct": 60.0,
            "roi_pct": 12.5,
        },
    )
    monkeypatch.setattr(subs, "_send_message", lambda token, chat_id, text: sent.append((chat_id, text)) or True)

    result = subs.process_admin_commands(
        database_url="db",
        telegram_token="tok",
        admin_chat_id="111",
        vip_chat_id="-100vip",
        confirm=False,
    )

    assert result["processed"] == 1
    assert "4" in sent[0][1]
    assert "60.0%" in sent[0][1]
    assert "+12.5%" in sent[0][1]


def test_morning_targets_vip_and_free():
    assert get_morning_targets("-100vip", "-100free", "admin") == ("-100vip", "-100free")


def test_morning_targets_vip_only():
    assert get_morning_targets("-100vip", "", "admin") == ("-100vip", None)


def test_morning_targets_free_only():
    assert get_morning_targets("", "-100free", "admin") == (None, "-100free")


def test_morning_targets_fallback():
    assert get_morning_targets("", "", "admin") == ("admin", None)


def test_audit_targets_vip_and_free():
    assert get_audit_targets("-100vip", "-100free", "admin") == ["-100vip", "-100free"]


def test_audit_targets_vip_only():
    assert get_audit_targets("-100vip", "", "admin") == ["-100vip"]


def test_audit_targets_fallback():
    assert get_audit_targets("", "", "admin") == ["admin"]


def test_free_message_includes_vip_invitation():
    tz = ZoneInfo("America/Bogota")
    msg = build_free_mensaje([], "2026-11-26", "2026-11-26 07:00", tz, "TEST", "@contacto")

    assert "VIP" in msg
    assert "@contacto" in msg
