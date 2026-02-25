"""Reusable UX actions for OpenClaw or CLI integration."""

from __future__ import annotations

from datetime import date
from typing import Any

from d_brain.bot.text_utils import fix_mojibake
from d_brain.config import Settings
from d_brain.services.session import SessionStore
from d_brain.services.storage import VaultStorage


def build_status_text(settings: Settings, user_id: int) -> str:
    storage = VaultStorage(settings.vault_path)
    session = SessionStore(settings.vault_path)

    today = date.today()
    content = storage.read_daily(today)
    if not content:
        return fix_mojibake(f"СЂСџвЂњвЂ¦ <b>{today}</b>\n\nР вЂ”Р В°Р С—Р С‘РЎРѓР ВµР в„– Р С—Р С•Р С”Р В° Р Р…Р ВµРЎвЂљ.")

    lines = content.strip().split("\n")
    entries = [line for line in lines if line.startswith("## ")]

    voice_count = sum(1 for e in entries if "[voice]" in e)
    text_count = sum(1 for e in entries if "[text]" in e)
    photo_count = sum(1 for e in entries if "[photo]" in e)
    forward_count = sum(1 for e in entries if "[forward from:" in e)
    total = len(entries)

    week_stats = ""
    stats = session.get_stats(user_id, days=7)
    if stats:
        week_stats = "\n\n<b>Р вЂ”Р В° 7 Р Т‘Р Р…Р ВµР в„–:</b>"
        for entry_type, count in sorted(stats.items()):
            week_stats += f"\nРІР‚Сћ {entry_type}: {count}"

    return fix_mojibake(
        f"СЂСџвЂњвЂ¦ <b>{today}</b>\n\n"
        f"Р вЂ™РЎРѓР ВµР С–Р С• Р В·Р В°Р С—Р С‘РЎРѓР ВµР в„–: <b>{total}</b>\n"
        f"- СЂСџР‹В¤ Р вЂњР С•Р В»Р С•РЎРѓР С•Р Р†РЎвЂ№РЎвЂ¦: {voice_count}\n"
        f"- СЂСџвЂ™В¬ Р СћР ВµР С”РЎРѓРЎвЂљР С•Р Р†РЎвЂ№РЎвЂ¦: {text_count}\n"
        f"- СЂСџвЂњВ· Р В¤Р С•РЎвЂљР С•: {photo_count}\n"
        f"- в†©пёЏ РџРµСЂРµСЃР»Р°РЅРЅС‹С…: {forward_count}"
        f"{week_stats}"
    )


def build_help_text() -> str:
    return fix_mojibake(
        "<b>РљР°Рє РїРѕР»СЊР·РѕРІР°С‚СЊСЃСЏ d-brain:</b>\n\n"
        "1. РћС‚РїСЂР°РІСЊ РіРѕР»РѕСЃРѕРІРѕРµ вЂ” Р±СѓРґРµС‚ СЂР°СЃРїРѕР·РЅР°РЅРѕ Рё СЃРѕС…СЂР°РЅРµРЅРѕ\n"
        "2. РћС‚РїСЂР°РІСЊ С‚РµРєСЃС‚ вЂ” Р±СѓРґРµС‚ СЃРѕС…СЂР°РЅРµРЅ РєР°Рє РµСЃС‚СЊ\n"
        "3. РћС‚РїСЂР°РІСЊ С„РѕС‚Рѕ вЂ” СЃРѕС…СЂР°РЅРёС‚СЃСЏ РІРѕ РІР»РѕР¶РµРЅРёСЏС…\n"
        "4. РџРµСЂРµС€Р»Рё СЃРѕРѕР±С‰РµРЅРёРµ вЂ” СЃРѕС…СЂР°РЅРёС‚СЃСЏ СЃ РёСЃС‚РѕС‡РЅРёРєРѕРј\n\n"
        "РСЃРїРѕР»СЊР·СѓР№ /process РґР»СЏ РѕР±СЂР°Р±РѕС‚РєРё РґРЅРµРІРЅС‹С… Р·Р°РјРµС‚РѕРє.\n\n"
        "<b>РљРѕРјР°РЅРґС‹:</b>\n"
        "/status - СЃС‚Р°С‚СѓСЃ РґРЅСЏ\n"
        "/process - РѕР±СЂР°Р±РѕС‚Р°С‚СЊ РґРЅРµРІРЅС‹Рµ Р·Р°РјРµС‚РєРё\n"
        "/do - РїСЂРѕРёР·РІРѕР»СЊРЅС‹Р№ Р·Р°РїСЂРѕСЃ\n"
        "/weekly - РЅРµРґРµР»СЊРЅС‹Р№ РґР°Р№РґР¶РµСЃС‚\n"
        "/plan add <title>\n"
        "/plan list\n"
        "/reminder list\n"
        "/note <text or url>\n"
        "/book add <text or url>\n"
        "/book list\n"
        "/philosophy add <text or url>\n"
        "/philosophy list\n"
        "/inbox add <text or url>\n"
        "/inbox list\n"
        "/inbox summarize <id>\n"
        "/inbox save <id> [title]\n"
        "/word add <word>\n"
        "/word list\n"
        "/topic add <name>\n"
        "/topic list\n"
        "/news latest\n"
        "/health add <title>\n"
        "/health list\n"
        "/web search <query>\n"
        "/web summarize <url>\n"
        "/youtube transcript <url>\n"
        "/reflect start (routes voice/text to reflection)\n"
        "/reflect add <session_id> <text>\n"
        "/reflect close <session_id> [summary]\n"
        "/digest latest\n"
        "/usage\n"
        "/tutor start [target_minutes]\n"
        "/tutor stop\n"
        "/tutor status"
    )


def build_plan_stub() -> str:
    return fix_mojibake("TODO: OpenClaw plan actions not migrated yet.")


def build_note_stub() -> str:
    return fix_mojibake("TODO: OpenClaw note/inbox actions not migrated yet.")


def build_reflection_stub() -> str:
    return fix_mojibake("TODO: OpenClaw reflection actions not migrated yet.")


def build_status_payload(settings: Settings, user_id: int) -> dict[str, Any]:
    return {"text": build_status_text(settings, user_id), "parse_mode": "HTML"}
