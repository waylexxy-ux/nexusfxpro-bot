"""
NEXUS FX — Telegram Subscription Bot
======================================
@NexusFXTrading_bot

Handles:
• Code verification for 3-month and 1-year subscribers
• Auto-generates single-use Telegram group invite links
• Kicks expired members every 6 hours automatically
• Tells 7d/30d subscribers they have web-terminal-only access
"""

import asyncio
import logging
import os
import re
import requests
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError

# ── CONFIG ────────────────────────────────────────────────────────────────────
BOT_TOKEN    = os.environ.get("BOT_TOKEN",    "8676005076:AAHgSrBVzxB1GYiK1i_DOwnXIV7PgDi7acE")
GROUP_ID     = int(os.environ.get("GROUP_ID", "-1003914554167"))
FIREBASE_URL = os.environ.get("FIREBASE_URL", "https://nexusfx-71cdc-default-rtdb.firebaseio.com")
SITE_URL     = os.environ.get("SITE_URL",     "https://timely-dragon-b2b939.netlify.app")

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ── FIREBASE HELPERS ──────────────────────────────────────────────────────────
def fb_get(path: str):
    r = requests.get(f"{FIREBASE_URL}/{path}.json", timeout=10)
    return r.json() if r.ok else None

def fb_patch(path: str, data: dict) -> bool:
    r = requests.patch(f"{FIREBASE_URL}/{path}.json", json=data, timeout=10)
    return r.ok

# ── HANDLERS ──────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome to NEXUS FX Signals Bot!*\n\n"
        "To join the signals group, send your access code.\n"
        "Your code was emailed to you after subscribing.\n\n"
        "📝 *Format:* `XXXX-XXXX-XXXX`\n\n"
        "⚠️ Telegram group access requires a *3-Month* or *1-Year* plan.\n"
        "7-day and 30-day plans get web terminal access only.",
        parse_mode="Markdown",
    )


async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw  = update.message.text.strip().upper()
    user = update.message.from_user

    # ── Validate code format ──────────────────────────────────────────────────
    if not re.match(r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$", raw):
        await update.message.reply_text(
            "❓ That doesn't look like an access code.\n"
            "Your code format is: `XXXX-XXXX-XXXX`\n\n"
            "Check your subscription email or type /start for help.",
            parse_mode="Markdown",
        )
        return

    code_key = raw.replace("-", "_")
    data     = fb_get(f"codes/{code_key}")

    # ── Code not found ────────────────────────────────────────────────────────
    if not data:
        await update.message.reply_text(
            "❌ *Code not found.*\n\n"
            "Double-check your email for the correct code, or contact the admin.",
            parse_mode="Markdown",
        )
        return

    # ── Plan check — 7d/30d gets web terminal only ────────────────────────────
    if not data.get("nexusAccess", False):
        tier      = data.get("tier", "30d")
        tier_name = "7-Day" if tier == "7d" else "30-Day"
        await update.message.reply_text(
            f"⚠️ *{tier_name} Plan — Web Terminal Access Only*\n\n"
            f"Your plan includes access to the NEXUS FX web terminal, "
            f"but not the Telegram signals group.\n\n"
            f"🖥 *Access your terminal here:*\n{SITE_URL}\n\n"
            f"To upgrade to full group access, contact the admin and request "
            f"a 3-Month or 1-Year plan.",
            parse_mode="Markdown",
        )
        return

    # ── Expiry check ──────────────────────────────────────────────────────────
    now_ms   = int(datetime.now(timezone.utc).timestamp() * 1000)
    expiry   = data.get("expiry", 0)
    if now_ms > expiry:
        exp_date = datetime.fromtimestamp(expiry / 1000, tz=timezone.utc).strftime("%d %b %Y")
        await update.message.reply_text(
            f"❌ *Subscription Expired*\n\n"
            f"Your subscription expired on *{exp_date}*.\n\n"
            f"To renew:\n"
            f"1. Visit {SITE_URL}\n"
            f"2. Click *REQUEST ACCESS*\n"
            f"3. Send your new code here to rejoin the group.",
            parse_mode="Markdown",
        )
        return

    # ── Already used ──────────────────────────────────────────────────────────
    stored_uid = data.get("telegramUserId")
    if stored_uid:
        if str(stored_uid) == str(user.id):
            await update.message.reply_text(
                "✅ *You already have group access!*\n\n"
                "Search for the group in Telegram.\n"
                "If you were removed, contact the admin.",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                "⚠️ This code has already been used by another account.\n"
                "Contact the admin if you believe this is an error.",
                parse_mode="Markdown",
            )
        return

    # ── All checks passed — generate single-use invite link ──────────────────
    try:
        invite = await context.bot.create_chat_invite_link(
            chat_id=GROUP_ID,
            member_limit=1,
            expire_date=int(expiry / 1000),   # link expires with subscription
            name=f"NXS-{raw[:8]}",
        )

        # Store Telegram user ID in Firebase
        fb_patch(f"codes/{code_key}", {
            "telegramUserId":   user.id,
            "telegramUsername": user.username or "",
            "groupJoinedAt":    now_ms,
            "groupKicked":      False,
        })

        tier      = data.get("tier", "3m")
        tier_name = "3-Month" if tier == "3m" else "1-Year"
        exp_date  = datetime.fromtimestamp(expiry / 1000, tz=timezone.utc).strftime("%d %b %Y")

        await update.message.reply_text(
            f"✅ *Access Granted — NEXUS FX Signals!*\n\n"
            f"📊 Plan: *{tier_name}*\n"
            f"📅 Valid until: *{exp_date}*\n\n"
            f"👇 Click the link below to join your signals group:\n"
            f"{invite.invite_link}\n\n"
            f"⚠️ *Single-use link* — do not share it.\n"
            f"🖥 Web terminal: {SITE_URL}",
            parse_mode="Markdown",
        )

        log.info(f"Granted group access: user={user.id} ({user.username}) code={raw}")

    except TelegramError as e:
        log.error(f"Invite link error for user={user.id}: {e}")
        await update.message.reply_text(
            "⚠️ There was an issue generating your invite link.\n"
            "Please try again in a moment or contact the admin."
        )


# ── AUTO-KICK JOB ─────────────────────────────────────────────────────────────
async def check_expiry(context: ContextTypes.DEFAULT_TYPE):
    """Runs every 6 hours. Kicks expired members and notifies them."""
    log.info("Running expiry check...")
    now_ms    = int(datetime.now(timezone.utc).timestamp() * 1000)
    all_codes = fb_get("codes") or {}
    kicked    = 0

    for code_key, data in all_codes.items():
        if not isinstance(data, dict):
            continue

        uid    = data.get("telegramUserId")
        kicked_already = data.get("groupKicked", False)

        # Only process active group members
        if not uid or kicked_already:
            continue

        # Skip if not expired
        if now_ms <= data.get("expiry", 0):
            continue

        # Kick from group
        try:
            await context.bot.ban_chat_member(chat_id=GROUP_ID, user_id=int(uid))
            await asyncio.sleep(1)
            # Unban immediately so they can rejoin if they renew
            await context.bot.unban_chat_member(chat_id=GROUP_ID, user_id=int(uid))

            # Mark as kicked in Firebase
            fb_patch(f"codes/{code_key}", {"groupKicked": True})
            kicked += 1

            # Notify the user
            exp_date = datetime.fromtimestamp(
                data.get("expiry", 0) / 1000, tz=timezone.utc
            ).strftime("%d %b %Y")
            try:
                await context.bot.send_message(
                    chat_id=int(uid),
                    text=(
                        f"⏰ *NEXUS FX — Subscription Expired*\n\n"
                        f"Your subscription expired on *{exp_date}*.\n"
                        f"You have been removed from the signals group.\n\n"
                        f"*To renew and rejoin:*\n"
                        f"1. Visit {SITE_URL}\n"
                        f"2. Request a new subscription\n"
                        f"3. Message this bot with your new code"
                    ),
                    parse_mode="Markdown",
                )
            except TelegramError:
                pass  # User may have blocked the bot

            log.info(f"Kicked expired member: uid={uid}")

        except TelegramError as e:
            log.warning(f"Could not kick uid={uid}: {e}")

    if kicked:
        log.info(f"Expiry check complete — kicked {kicked} member(s).")


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code))

    # Schedule expiry check every 6 hours
    app.job_queue.run_repeating(check_expiry, interval=21_600, first=60)

    log.info("NEXUS FX Bot is running — @NexusFXTrading_bot")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
