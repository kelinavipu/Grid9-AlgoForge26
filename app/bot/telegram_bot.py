import logging
import os
import uuid
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, Voice
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from bot.state_machine import (
    STATES,
    FIELD_ORDER,
    get_prompt_for_state,
    get_state_key,
    parse_date,
    parse_time,
    parse_age,
    parse_phone,
)
from stt.transcriber import transcribe_audio
from bot.tts_sender import send_voice_reply
from excel.manager import write_appointment, get_appointment_by_id, is_slot_taken
from email_module.sender import send_doctor_email

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── State parsing map — maps state to its parser function ─────────────────────

STATE_PARSERS = {
    STATES.ASK_AGE: parse_age,
    STATES.ASK_PHONE: parse_phone,
    STATES.ASK_DATE: parse_date,
    STATES.ASK_TIME: parse_time,
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point. Greets patient and asks for their name."""
    context.user_data.clear()  # Reset any previous conversation state
    context.user_data["current_state"] = STATES.ASK_NAME
    greeting = (
        "नमस्ते! मैं आपका अपॉइंटमेंट सहायक हूँ। "
        "मैं आपसे कुछ जानकारी लूँगा। "
        "कृपया अपना पूरा नाम बताएं।"
    )
    await send_voice_reply(update, context, greeting)
    return STATES.ASK_NAME


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Processes a voice message at any state.
    Steps:
      1. Download the .oga file from Telegram
      2. Transcribe with Whisper (sends .oga directly — no WAV conversion)
      3. Parse/clean the transcription based on current state
      4. Store the transcription in context.user_data
      5. Advance to the next state, prompting the patient for the next field
      6. If all fields collected, write to Excel and email doctor
    Returns the next STATES integer.
    """
    current_state = context.user_data.get("current_state", STATES.ASK_NAME)
    state_key = get_state_key(current_state)

    # ── Step 1: Download voice file ───────────────────────────────────────────
    voice: Voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)

    temp_dir = os.getenv("TEMP_AUDIO_DIR", "temp_audio/")
    os.makedirs(temp_dir, exist_ok=True)

    oga_path = os.path.join(temp_dir, f"{uuid.uuid4()}.oga")
    await file.download_to_drive(oga_path)

    # ── Step 2: Transcribe via OpenAI Whisper API ────────────────────────────
    try:
        transcription = transcribe_audio(oga_path)
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        error_msg = "माफ करें, आवाज़ सुनने में समस्या हुई। कृपया दोबारा बोलें।"
        await send_voice_reply(update, context, error_msg)
        return current_state  # Stay in same state, retry
    finally:
        # Clean up temp .oga file regardless of success/failure
        if os.path.exists(oga_path):
            os.remove(oga_path)

    # ── Step 3: Parse transcription based on state ────────────────────────────
    parser = STATE_PARSERS.get(current_state)
    if parser:
        parsed_value = parser(transcription)
    else:
        parsed_value = transcription

    # ── Step 4: Store transcription ───────────────────────────────────────────
    context.user_data[state_key] = parsed_value
    logger.info(f"State: {state_key} | Raw: '{transcription}' | Parsed: '{parsed_value}'")

    # ── Step 5: Advance to next state ─────────────────────────────────────────
    next_state = get_next_state(current_state)

    if next_state is None:
        # ── All fields collected — finalize appointment ────────────────────
        return await finalize_appointment(update, context)
    else:
        context.user_data["current_state"] = next_state
        prompt = get_prompt_for_state(next_state)
        await send_voice_reply(update, context, prompt)
        return next_state


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Same logic as handle_voice but input comes from typed text.
    This is important for accessibility — some patients may prefer typing.
    """
    current_state = context.user_data.get("current_state", STATES.ASK_NAME)
    state_key = get_state_key(current_state)

    transcription = update.message.text.strip()

    # Parse transcription based on state
    parser = STATE_PARSERS.get(current_state)
    if parser:
        parsed_value = parser(transcription)
    else:
        parsed_value = transcription

    context.user_data[state_key] = parsed_value
    logger.info(f"State: {state_key} | Text input: '{transcription}' | Parsed: '{parsed_value}'")

    next_state = get_next_state(current_state)

    if next_state is None:
        return await finalize_appointment(update, context)
    else:
        context.user_data["current_state"] = next_state
        prompt = get_prompt_for_state(next_state)
        await send_voice_reply(update, context, prompt)
        return next_state


async def finalize_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Called when all fields have been collected.
    1. Check for scheduling conflicts
    2. Write to Excel
    3. Send doctor email
    4. Thank the patient
    Returns ConversationHandler.END or STATES.ASK_DATE on conflict.
    """
    chat_id = update.effective_chat.id
    user_data = context.user_data

    preferred_date = user_data.get("preferred_date", "")
    preferred_time = user_data.get("preferred_time", "")

    # ── Conflict check ────────────────────────────────────────────────────────
    if is_slot_taken(preferred_date, preferred_time):
        conflict_msg = (
            f"माफ करें, {preferred_date} को {preferred_time} बजे का समय पहले से बुक है। "
            "कृपया कोई दूसरा समय या तारीख चुनें।"
        )
        await send_voice_reply(update, context, conflict_msg)

        # Reset only date and time fields so patient can re-enter them
        context.user_data.pop("preferred_date", None)
        context.user_data.pop("preferred_time", None)
        context.user_data["current_state"] = STATES.ASK_DATE

        await send_voice_reply(update, context, get_prompt_for_state(STATES.ASK_DATE))
        return STATES.ASK_DATE

    # ── No conflict — proceed with booking ───────────────────────────────────
    appointment_id = str(uuid.uuid4())
    security_token = str(uuid.uuid4())
    now = datetime.now().isoformat(timespec="seconds")

    appointment = {
        "appointment_id": appointment_id,
        "security_token": security_token,
        "patient_name": user_data.get("patient_name", ""),
        "patient_age": user_data.get("patient_age", ""),
        "patient_phone": user_data.get("patient_phone", ""),
        "telegram_chat_id": chat_id,
        "preferred_date": preferred_date,
        "preferred_time": preferred_time,
        "symptoms": user_data.get("symptoms", ""),
        "status": "Pending",
        "confirmed_date": "",
        "confirmed_time": "",
        "doctor_notes": "",
        "created_at": now,
        "updated_at": now,
    }

    # ── Write to Excel ────────────────────────────────────────────────────────
    try:
        write_appointment(appointment)
        logger.info(f"Appointment written to Excel: {appointment_id}")
    except Exception as e:
        logger.error(f"Excel write failed: {e}", exc_info=True)
        error_msg = (
            "माफ करें, अपॉइंटमेंट सेव करने में समस्या हुई। "
            "कृपया दोबारा कोशिश करें।"
        )
        await send_voice_reply(update, context, error_msg)
        return ConversationHandler.END  # Do not proceed to email if save failed

    # ── Send doctor email (failure here does NOT block the patient) ───────────
    try:
        send_doctor_email(appointment)
        logger.info(f"Doctor email sent for appointment: {appointment_id}")
    except Exception as e:
        logger.error(f"Email sending failed: {e}")
        # Appointment is already saved — continue and thank patient

    # ── Thank the patient ─────────────────────────────────────────────────────
    try:
        thanks_msg = (
            f"धन्यवाद {appointment['patient_name']} जी! "
            f"आपका अपॉइंटमेंट {appointment['preferred_date']} को "
            f"{appointment['preferred_time']} बजे के लिए अनुरोध किया गया है। "
            "डॉक्टर की पुष्टि होने पर आपको सूचित किया जाएगा।"
        )
        await send_voice_reply(update, context, thanks_msg)
    except Exception as e:
        logger.error(f"Failed to send thank-you message: {e}")

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the current conversation."""
    context.user_data.clear()
    await send_voice_reply(
        update, context,
        "अपॉइंटमेंट रद्द किया गया। फिर से शुरू करने के लिए /start टाइप करें।"
    )
    return ConversationHandler.END


def get_next_state(current_state: int):
    """Returns the next state integer, or None if all fields are done."""
    idx = FIELD_ORDER.index(current_state)
    if idx + 1 < len(FIELD_ORDER):
        return FIELD_ORDER[idx + 1]
    return None


def build_application() -> Application:
    """Builds and returns the configured Application object."""
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env")

    app = ApplicationBuilder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            STATES.ASK_NAME: [
                MessageHandler(filters.VOICE, handle_voice),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
            ],
            STATES.ASK_AGE: [
                MessageHandler(filters.VOICE, handle_voice),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
            ],
            STATES.ASK_PHONE: [
                MessageHandler(filters.VOICE, handle_voice),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
            ],
            STATES.ASK_DATE: [
                MessageHandler(filters.VOICE, handle_voice),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
            ],
            STATES.ASK_TIME: [
                MessageHandler(filters.VOICE, handle_voice),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
            ],
            STATES.ASK_SYMPTOMS: [
                MessageHandler(filters.VOICE, handle_voice),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)
    return app
