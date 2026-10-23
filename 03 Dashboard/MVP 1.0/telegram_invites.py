"""
(C) telegram_invites.py — Personalisierte Telegram Einladungslinks

Generiert Einmal-Einladungslinks via Telegram Bot API (createChatInviteLink).
Jeder Link kann nur von einer Person genutzt werden (member_limit=1).

Verwendet denselben Bot-Token wie der Signal Bot.
"""

import os
import logging
import aiohttp

logger = logging.getLogger(__name__)


def _to_long_link(link: str) -> str:
    """Erzwingt die lange telegram.me-Form statt t.me.

    Der t.me-Redirect faellt global gelegentlich aus; telegram.me ist die
    ausgeschriebene, robustere Variante. Gilt fuer JEDEN hier erstellten Link.
    """
    if not link:
        return link
    return (link
            .replace("https://t.me/", "https://telegram.me/")
            .replace("http://t.me/", "https://telegram.me/"))


BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
PAID_GROUP_ID = os.getenv("SIGNAL_PAID_GROUP_ID", "")


async def create_invite_link(group_id: str, name: str = "") -> str | None:
    """
    Erstellt einen Einmal-Einladungslink fuer eine Telegram-Gruppe.

    Args:
        group_id: Chat-ID der Telegram-Gruppe
        name: Optionaler Name fuer den Link (z.B. Kundenname, wird im Admin-Panel sichtbar)

    Returns:
        Invite-Link als String oder None bei Fehler
    """
    if not BOT_TOKEN:
        logger.error("[TELEGRAM] BOT_TOKEN nicht konfiguriert")
        return None

    if not group_id:
        logger.error("[TELEGRAM] Keine Group-ID angegeben")
        return None

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/createChatInviteLink"
    payload = {
        "chat_id": int(group_id),
        "member_limit": 1,
    }
    if name:
        payload["name"] = name[:32]  # Telegram max 32 Zeichen

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                if data.get("ok"):
                    link = _to_long_link(data["result"]["invite_link"])
                    logger.info(f"[TELEGRAM] Invite-Link erstellt: {link} (name={name})")
                    return link
                else:
                    logger.error(f"[TELEGRAM] createChatInviteLink fehlgeschlagen: {data}")
                    return None
    except Exception as e:
        logger.error(f"[TELEGRAM] Fehler beim Erstellen des Invite-Links: {e}")
        return None


async def create_paid_invite(customer_name: str = "") -> str | None:
    """Erstellt Einmal-Link fuer die Paid Signal-Gruppe."""
    return await create_invite_link(PAID_GROUP_ID, name=customer_name)


# ==========================================================================
# KICK — Mitglied aus Gruppe entfernen (Abo gekuendigt/expired/refunded)
# ==========================================================================

async def kick_from_paid_group(telegram_chat_id: str) -> bool:
    """
    Entfernt ein Mitglied aus der Paid Signal-Gruppe.

    Verwendet banChatMember + unbanChatMember (Kick ohne permanenten Ban).
    So kann der User bei erneutem Abo wieder eingeladen werden.

    Args:
        telegram_chat_id: Telegram User-ID des Mitglieds

    Returns:
        True wenn erfolgreich gekickt, False bei Fehler
    """
    if not BOT_TOKEN or not PAID_GROUP_ID or not telegram_chat_id:
        logger.warning("[TELEGRAM] Kick nicht moeglich — fehlende Konfiguration")
        return False

    try:
        async with aiohttp.ClientSession() as session:
            # Schritt 1: Ban (entfernt aus Gruppe)
            ban_url = f"https://api.telegram.org/bot{BOT_TOKEN}/banChatMember"
            ban_payload = {
                "chat_id": int(PAID_GROUP_ID),
                "user_id": int(telegram_chat_id),
            }
            async with session.post(ban_url, json=ban_payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                ban_result = await resp.json()
                if not ban_result.get("ok"):
                    logger.warning(f"[TELEGRAM] banChatMember fehlgeschlagen: {ban_result}")
                    return False

            # Schritt 2: Unban (hebt permanenten Ban auf, User kann wieder eingeladen werden)
            unban_url = f"https://api.telegram.org/bot{BOT_TOKEN}/unbanChatMember"
            unban_payload = {
                "chat_id": int(PAID_GROUP_ID),
                "user_id": int(telegram_chat_id),
                "only_if_banned": True,
            }
            async with session.post(unban_url, json=unban_payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                unban_result = await resp.json()
                if not unban_result.get("ok"):
                    logger.warning(f"[TELEGRAM] unbanChatMember fehlgeschlagen: {unban_result}")
                    # Kick war trotzdem erfolgreich, Ban bleibt halt bestehen
                    # Bei erneutem Abo muss dann manuell entbannt werden

            logger.info(f"[TELEGRAM] User {telegram_chat_id} aus Paid-Gruppe gekickt")
            return True

    except Exception as e:
        logger.error(f"[TELEGRAM] Kick fehlgeschlagen: {e}")
        return False


# ==========================================================================
# RUECKKEHRER — Ban aufheben + Admin-Info (2026-09-11)
# ==========================================================================

SCALP_GROUP_ID = os.getenv("SIGNAL_SCALP_GROUP_ID", "")
ADMIN_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


async def unban_from_groups(telegram_user_id: str) -> dict:
    """Hebt einen Ban in Main-Gruppe + Scalp-Channel auf.

    only_if_banned=True -> aktive Mitglieder bleiben unberuehrt (kein versehentlicher Kick).
    Rueckgabe: {"main": bool, "scalp": bool} fuer jede konfigurierte Gruppe.
    """
    results: dict = {}
    if not BOT_TOKEN or not telegram_user_id:
        return results
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/unbanChatMember"
    async with aiohttp.ClientSession() as session:
        for label, gid in (("main", PAID_GROUP_ID), ("scalp", SCALP_GROUP_ID)):
            if not gid:
                continue
            try:
                payload = {"chat_id": int(gid), "user_id": int(telegram_user_id), "only_if_banned": True}
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    results[label] = bool(data.get("ok"))
                    if not data.get("ok"):
                        logger.warning(f"[TELEGRAM] unbanChatMember {label} fehlgeschlagen: {data}")
            except Exception as e:
                results[label] = False
                logger.error(f"[TELEGRAM] unbanChatMember {label} Fehler: {e}")
    logger.info(f"[TELEGRAM] Entbannung {telegram_user_id}: {results}")
    return results


async def notify_admin(text: str) -> bool:
    """Kurze Info-DM an Max (TELEGRAM_CHAT_ID). Best-effort, wirft nie."""
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        return False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": ADMIN_CHAT_ID, "text": text[:4000], "disable_web_page_preview": True},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                return bool(data.get("ok"))
    except Exception as e:
        logger.error(f"[TELEGRAM] Admin-Info fehlgeschlagen: {e}")
        return False
