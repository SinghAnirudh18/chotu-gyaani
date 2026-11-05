"""Telegram bot integration for Chotu-Gyani.

LOGIN FLOW (first time / after /logout):
  /start → ask for email → ask for password → verify → linked to account

After login, shopkeepers can:
  - Send text messages in Hindi / English / Hinglish → get text reply
  - Send voice notes → auto-transcribed via Gnani STT → reply with voice note via Gnani TTS
  - Confirm / Cancel pending actions via inline-keyboard buttons
  - /logout to clear session
  - /lang hi|en to switch language

Multi-tenant: each Telegram chat_id is linked to one (user, business) pair
after a successful password login.  Session is kept in-memory; bot restart
requires re-login.  For production, persist to DB (TelegramSession table).
"""
from __future__ import annotations

import asyncio
import io
import logging
import subprocess
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import verify_password
from app.db.models import Business, BusinessMember, Conversation, User
from app.db.session import get_sessionmaker
from app.providers.stt import get_stt
from app.providers.tts import get_tts
from app.services import action_service
from app.services.pipeline import process_user_message
from app.api.deps import Ctx

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-chat state machine
# ---------------------------------------------------------------------------

class LoginState(Enum):
    LOGGED_OUT    = auto()   # fresh / after /logout
    AWAIT_EMAIL   = auto()   # bot asked for email
    AWAIT_PASSWORD = auto()  # bot asked for password
    LOGGED_IN     = auto()   # active session


@dataclass
class ChatSession:
    state: LoginState = LoginState.LOGGED_OUT
    pending_email: str = ""                      # email entered, awaiting password
    user_id: uuid.UUID | None = None
    business_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    language: str = "hi"                         # preferred reply language


# In-memory store  {chat_id: ChatSession}
_sessions: dict[int, ChatSession] = {}


def _get_session(chat_id: int) -> ChatSession:
    if chat_id not in _sessions:
        _sessions[chat_id] = ChatSession()
    return _sessions[chat_id]


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def _ogg_to_wav(data: bytes) -> bytes:
    """OGG/OPUS (Telegram voice) → 16 kHz mono WAV."""
    proc = subprocess.run(
        ["ffmpeg", "-y", "-i", "pipe:0", "-ar", "16000", "-ac", "1", "-f", "wav", "pipe:1"],
        input=data, capture_output=True,
    )
    return proc.stdout if proc.stdout else data


def _wav_to_ogg(data: bytes) -> bytes:
    """WAV → OGG/OPUS for Telegram voice reply."""
    proc = subprocess.run(
        ["ffmpeg", "-y", "-i", "pipe:0", "-c:a", "libopus", "-b:a", "32k", "-f", "ogg", "pipe:1"],
        input=data, capture_output=True,
    )
    return proc.stdout if proc.stdout else data


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _authenticate_user(email: str, password: str, db: AsyncSession) -> User | None:
    """Return User if credentials are valid, else None."""
    user = (await db.execute(
        select(User).where(User.email == email.lower().strip())
    )).scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def _pick_business(user: User, db: AsyncSession) -> tuple[Business, str] | None:
    """Return (business, role) — the first active business the user belongs to."""
    row = (await db.execute(
        select(Business, BusinessMember.role)
        .join(BusinessMember, BusinessMember.business_id == Business.id)
        .where(BusinessMember.user_id == user.id, Business.archived_at.is_(None))
        .order_by(Business.created_at)
        .limit(1)
    )).first()
    return row  # (Business, role) or None


async def _get_or_create_conversation(
    chat_id: int, user: User, business: Business, db: AsyncSession
) -> Conversation:
    """Find or create the persistent bot conversation for this chat_id."""
    tg_title = f"telegram:{chat_id}"
    conv = (await db.execute(
        select(Conversation).where(
            Conversation.business_id == business.id,
            Conversation.user_id == user.id,
            Conversation.title == tg_title,
        ).limit(1)
    )).scalar_one_or_none()

    if conv is None:
        conv = Conversation(
            business_id=business.id,
            user_id=user.id,
            title=tg_title,
            language=business.default_language,
            state={},
        )
        db.add(conv)
        await db.commit()
        await db.refresh(conv)
    return conv


async def _build_ctx(session: ChatSession, db: AsyncSession) -> tuple[Ctx, Conversation] | None:
    """Build Ctx + Conversation from a logged-in session."""
    if not session.user_id or not session.business_id or not session.conversation_id:
        return None
    user = await db.get(User, session.user_id)
    business = await db.get(Business, session.business_id)
    conv = await db.get(Conversation, session.conversation_id)
    if not user or not business or not conv:
        return None
    row = (await db.execute(
        select(BusinessMember.role).where(
            BusinessMember.user_id == user.id,
            BusinessMember.business_id == business.id,
        )
    )).scalar_one_or_none()
    role = row or "owner"
    ctx = Ctx(db=db, user=user, business=business, role=role)
    return ctx, conv


# ---------------------------------------------------------------------------
# Login flow handlers
# ---------------------------------------------------------------------------

async def _handle_start(update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    chat_id = update.effective_chat.id
    session = _get_session(chat_id)

    if session.state == LoginState.LOGGED_IN:
        await update.message.reply_text(
            "✅ आप पहले से लॉग इन हैं!\n\n"
            "बस कुछ भी लिखें या वॉइस नोट भेजें।\n"
            "_/logout_ करने के लिए `/logout` लिखें।",
            parse_mode="Markdown",
        )
        return

    session.state = LoginState.AWAIT_EMAIL
    session.pending_email = ""
    await update.message.reply_text(
        "🙏 *Chotu Gyani में आपका स्वागत है!*\n\n"
        "लॉग इन करने के लिए अपना *Email ID* लिखें:\n\n"
        "_Please enter your registered email address:_",
        parse_mode="Markdown",
    )


async def _handle_logout(update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    chat_id = update.effective_chat.id
    session = _get_session(chat_id)
    session.state = LoginState.LOGGED_OUT
    session.user_id = None
    session.business_id = None
    session.conversation_id = None
    session.pending_email = ""
    await update.message.reply_text(
        "👋 लॉग आउट हो गया।\nफिर से शुरू करने के लिए `/start` लिखें।",
        parse_mode="Markdown",
    )


async def _handle_help(update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    await update.message.reply_text(
        "🤖 *Chotu Gyani — Help*\n\n"
        "Commands:\n"
        "/start  — लॉग इन / Welcome\n"
        "/logout — लॉग आउट\n"
        "/help   — यह मैसेज\n"
        "/lang hi — हिंदी में जवाब\n"
        "/lang en — Reply in English\n\n"
        "Features:\n"
        "• Balance check → _rakesh ka kitna baaki hai_\n"
        "• Record payment → _ramesh ne 3000 diye_\n"
        "• Overdue list  → _overdue bills dikhao_\n"
        "• Reminder      → _kal 9 baje suresh ko yaad dilao_\n"
        "• Commitment    → _suresh kal 5000 dega_\n"
        "• New customer  → _ek customer banao raju naam ka_\n"
        "• Voice note    → Send a voice message in Hindi/English",
        parse_mode="Markdown",
    )


async def _handle_lang(update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    chat_id = update.effective_chat.id
    session = _get_session(chat_id)
    args = context.args or []
    lang = args[0].lower() if args else "hi"
    if lang not in ("hi", "en"):
        await update.message.reply_text("Supported: /lang hi  or  /lang en")
        return
    session.language = lang
    if lang == "hi":
        await update.message.reply_text("ठीक है, मैं हिंदी में जवाब दूँगा। 👍")
    else:
        await update.message.reply_text("OK, I'll reply in English. 👍")


# ---------------------------------------------------------------------------
# Main message router (handles login flow + normal chat)
# ---------------------------------------------------------------------------

CONFIRM_BTN = "✅ Confirm / पुष्टि करें"
CANCEL_BTN  = "❌ Cancel / रद्द करें"


async def _handle_text(update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    chat_id = update.effective_chat.id
    session = _get_session(chat_id)
    text = (update.message.text or "").strip()
    if not text:
        return

    # --- LOGIN STATE MACHINE ---

    if session.state == LoginState.LOGGED_OUT:
        # Treat any text as a prompt to start login
        await update.message.reply_text(
            "👋 पहले लॉग इन करें। `/start` लिखें।",
            parse_mode="Markdown",
        )
        return

    if session.state == LoginState.AWAIT_EMAIL:
        # Store email, ask for password
        session.pending_email = text.strip()
        session.state = LoginState.AWAIT_PASSWORD
        await update.message.reply_text(
            f"📧 Email मिला: `{session.pending_email}`\n\n"
            "अब अपना *Password* लिखें:\n_(Please enter your password)_",
            parse_mode="Markdown",
        )
        return

    if session.state == LoginState.AWAIT_PASSWORD:
        password = text.strip()
        # Try to delete the password message for security
        try:
            await update.message.delete()
        except Exception:
            pass

        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        sm = get_sessionmaker()
        async with sm() as db:
            user = await _authenticate_user(session.pending_email, password, db)
            if user is None:
                session.state = LoginState.AWAIT_EMAIL
                session.pending_email = ""
                await update.message.reply_text(
                    "❌ *Email या Password गलत है।*\n\n"
                    "कृपया फिर से अपना Email लिखें:\n"
                    "_(Wrong credentials. Please enter your email again)_",
                    parse_mode="Markdown",
                )
                return

            biz_row = await _pick_business(user, db)
            if biz_row is None:
                session.state = LoginState.LOGGED_OUT
                await update.message.reply_text(
                    "❌ इस account से कोई Business नहीं मिला।\n"
                    "_(No business found for this account)_",
                    parse_mode="Markdown",
                )
                return

            business, _role = biz_row
            conv = await _get_or_create_conversation(chat_id, user, business, db)

            session.state = LoginState.LOGGED_IN
            session.user_id = user.id
            session.business_id = business.id
            session.conversation_id = conv.id

        await update.message.reply_text(
            f"✅ *लॉग इन सफल!*\n\n"
            f"👤 {user.name}\n"
            f"🏪 {business.name}\n\n"
            "अब बोलें या लिखें — Hindi, English, या Hinglish में!\n"
            "🎙️ वॉइस नोट भी भेज सकते हैं।\n\n"
            "_/help के लिए `/help` लिखें | /logout के लिए `/logout`_",
            parse_mode="Markdown",
        )
        return

    # --- LOGGED IN: normal chat ---

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    reply, action = await _run_pipeline(session, text, session.language)

    if action is not None:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(CONFIRM_BTN, callback_data=f"confirm:{action.id}"),
            InlineKeyboardButton(CANCEL_BTN, callback_data=f"cancel:{action.id}"),
        ]])
        await update.message.reply_text(reply, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await update.message.reply_text(reply, parse_mode="Markdown")


async def _handle_voice(update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    chat_id = update.effective_chat.id
    session = _get_session(chat_id)

    if session.state != LoginState.LOGGED_IN:
        await update.message.reply_text(
            "👋 पहले लॉग इन करें। `/start` लिखें।",
            parse_mode="Markdown",
        )
        return

    await context.bot.send_chat_action(chat_id=chat_id, action="record_voice")

    # Download OGG from Telegram
    tg_file = await context.bot.get_file(update.message.voice.file_id)
    ogg_bytes = bytes(await tg_file.download_as_bytearray())

    # Convert OGG → WAV for Gnani STT
    wav_bytes = await asyncio.get_event_loop().run_in_executor(None, _ogg_to_wav, ogg_bytes)

    # STT
    try:
        transcript = await get_stt().transcribe(wav_bytes, session.language or "hi")
        text = transcript.text.strip()
        detected_lang = transcript.language or session.language
    except Exception as exc:
        logger.warning("telegram STT error: %s", exc)
        await update.message.reply_text(
            "🎙️ आवाज़ समझ नहीं आई। कृपया फिर से बोलें।\n"
            "_(Voice could not be understood, please try again.)_",
            parse_mode="Markdown",
        )
        return

    if not text:
        await update.message.reply_text("🎙️ आवाज़ खाली लगी। कृपया फिर से बोलें।")
        return

    # Echo transcription
    await update.message.reply_text(f"🎙️ _{text}_", parse_mode="Markdown")

    # Pipeline
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    reply, action = await _run_pipeline(session, text, detected_lang)

    # TTS
    await context.bot.send_chat_action(chat_id=chat_id, action="record_voice")
    ogg_reply: bytes | None = None
    try:
        audio_result = await get_tts().synthesize(reply, detected_lang or "hi", None)
        ogg_reply = await asyncio.get_event_loop().run_in_executor(None, _wav_to_ogg, audio_result.audio)
    except Exception as exc:
        logger.warning("telegram TTS error: %s", exc)

    if action is not None:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(CONFIRM_BTN, callback_data=f"confirm:{action.id}"),
            InlineKeyboardButton(CANCEL_BTN, callback_data=f"cancel:{action.id}"),
        ]])
        await update.message.reply_text(reply, reply_markup=keyboard, parse_mode="Markdown")
        if ogg_reply:
            await update.message.reply_voice(voice=io.BytesIO(ogg_reply))
    else:
        if ogg_reply:
            await update.message.reply_voice(
                voice=io.BytesIO(ogg_reply),
                caption=reply[:1024] if len(reply) > 100 else None,
            )
        else:
            await update.message.reply_text(reply, parse_mode="Markdown")


async def _handle_callback(update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
    """Handle Confirm / Cancel inline-keyboard callbacks."""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    if ":" not in data:
        return
    action_str, action_id_str = data.split(":", 1)
    try:
        action_id = uuid.UUID(action_id_str)
    except ValueError:
        await query.edit_message_text("❌ Invalid action ID.")
        return

    chat_id = update.effective_chat.id
    session = _get_session(chat_id)

    if session.state != LoginState.LOGGED_IN:
        await query.edit_message_text("⚠️ Session expired. Please /start again.")
        return

    sm = get_sessionmaker()
    async with sm() as db:
        result = await _build_ctx(session, db)
        if result is None:
            await query.edit_message_text("⚠️ Session error. Please /start again.")
            return
        ctx, conv = result
        try:
            if action_str == "confirm":
                action = await action_service.confirm(ctx, action_id)
                lang = conv.language or "hi"
                from app.utils.i18n import t
                summary = action.result.get("summary", "") if action.result else ""
                msg = t("confirmed", lang, summary=summary)
            else:
                await action_service.cancel(ctx, action_id)
                lang = conv.language or "hi"
                from app.utils.i18n import t
                msg = t("cancelled", lang)
        except Exception as exc:
            logger.warning("telegram callback error: %s", exc)
            msg = f"❌ Error: {exc}"

    await query.edit_message_text(msg, reply_markup=None)


# ---------------------------------------------------------------------------
# Pipeline runner (shared by text + voice)
# ---------------------------------------------------------------------------

async def _run_pipeline(session: ChatSession, text: str, lang_hint: str | None) -> tuple[str, object | None]:
    sm = get_sessionmaker()
    async with sm() as db:
        result = await _build_ctx(session, db)
        if result is None:
            return "⚠️ Session expired. Please /start again.", None
        ctx, conv = result
        pipeline_result = await process_user_message(ctx, conv, text, lang_hint, source="telegram_text")
        outcome = pipeline_result["outcome"]
        return outcome.reply, outcome.action


# ---------------------------------------------------------------------------
# Application factory & lifecycle
# ---------------------------------------------------------------------------

_app_instance = None   # telegram.ext.Application


async def start_telegram_bot() -> None:
    """Build and start the Telegram bot with long-polling.
    Called from FastAPI lifespan.  No-op if TELEGRAM_BOT_TOKEN is not set.
    """
    global _app_instance
    settings = get_settings()
    token = settings.telegram_bot_token
    if not token:
        logger.info("TELEGRAM_BOT_TOKEN not set — Telegram bot disabled")
        return

    from telegram.ext import (
        Application,
        CallbackQueryHandler,
        CommandHandler,
        MessageHandler,
        filters,
    )

    app = Application.builder().token(token).build()
    _app_instance = app

    app.add_handler(CommandHandler("start", _handle_start))
    app.add_handler(CommandHandler("logout", _handle_logout))
    app.add_handler(CommandHandler("help", _handle_help))
    app.add_handler(CommandHandler("lang", _handle_lang))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_text))
    app.add_handler(MessageHandler(filters.VOICE, _handle_voice))
    app.add_handler(CallbackQueryHandler(_handle_callback))

    logger.info("Starting Telegram bot (long-polling) …")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("Telegram bot polling started ✓")


async def stop_telegram_bot() -> None:
    """Gracefully stop the Telegram bot."""
    global _app_instance
    if _app_instance is None:
        return
    try:
        await _app_instance.updater.stop()
        await _app_instance.stop()
        await _app_instance.shutdown()
        logger.info("Telegram bot stopped")
    except Exception as exc:
        logger.warning("Error stopping Telegram bot: %s", exc)
    _app_instance = None
