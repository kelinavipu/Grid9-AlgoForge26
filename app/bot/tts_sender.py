import os
import uuid
import logging
from huggingface_hub import InferenceClient
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ContextTypes

load_dotenv()
logger = logging.getLogger(__name__)

HF_API_TOKEN = os.getenv("HF_API_TOKEN")
HF_TTS_MODEL = os.getenv("HF_TTS_MODEL", "mistralai/Voxtral-4B-TTS-2603")
TTS_LANGUAGE_HINT = os.getenv("TTS_LANGUAGE_HINT", "Hindi")
TEMP_AUDIO_DIR = os.getenv("TEMP_AUDIO_DIR", "temp_audio/")

# Initialise the HuggingFace Inference client once at module load time.
# The model is served remotely — it is NOT downloaded locally.
_hf_client = None


def _get_hf_client() -> InferenceClient:
    """Lazy-initialise and return the HF Inference client."""
    global _hf_client
    if _hf_client is None:
        if not HF_API_TOKEN:
            raise RuntimeError(
                "HF_API_TOKEN is not set in .env. "
                "Get a token at https://huggingface.co/settings/tokens"
            )
        _hf_client = InferenceClient(
            model=HF_TTS_MODEL,
            token=HF_API_TOKEN,
        )
        logger.info(f"HF Inference client initialised for TTS model: {HF_TTS_MODEL}")
    return _hf_client


def generate_tts_audio(text: str, language_hint: str = None) -> str:
    """
    Converts text to speech using the Hugging Face Inference API
    (mistralai/Voxtral-4B-TTS-2603) and saves the result as a .ogg file.

    The model is called REMOTELY via the HF Inference API.
    It is NOT run or downloaded locally.

    Args:
        text: The text to convert to speech.
        language_hint: Natural-language hint for voice/language, e.g. "Hindi".
                       Defaults to TTS_LANGUAGE_HINT from .env.

    Returns:
        Path to the generated .ogg audio file.

    Notes:
        - Voxtral returns raw audio bytes (wav/pcm). We save them as .ogg —
          Telegram accepts .ogg for voice messages.
        - The caller is responsible for deleting the file after sending.

    Raises:
        RuntimeError: If HF_API_TOKEN is not set.
        huggingface_hub.errors.HfHubHTTPError: On API call failure.
    """
    client = _get_hf_client()

    os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)

    hint = language_hint or TTS_LANGUAGE_HINT
    # Voxtral-4B-TTS accepts a plain text prompt. Prepend a language instruction
    # so the model produces speech in the correct language/accent.
    prompt = f"[{hint}] {text}"

    filename = f"tts_{uuid.uuid4()}.ogg"
    filepath = os.path.join(TEMP_AUDIO_DIR, filename)

    # text_to_speech() returns raw audio bytes from the Inference API.
    audio_bytes: bytes = client.text_to_speech(prompt)

    if not audio_bytes:
        raise ValueError("HF Inference API returned empty audio bytes.")

    with open(filepath, "wb") as f:
        f.write(audio_bytes)

    logger.info(f"TTS audio generated via HF Inference API: {filepath}")
    return filepath


async def send_voice_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    language_hint: str = None,
) -> None:
    """
    Generates TTS from text via Hugging Face Inference API and sends it
    as a voice message reply on Telegram.
    Also sends the text as a caption so users who cannot play audio can read it.

    Falls back to text-only message if TTS fails.

    Args:
        update: Telegram Update object
        context: Telegram context
        text: Text to speak
        language_hint: Optional language override (natural language, e.g. "Hindi")
    """
    audio_path = None
    try:
        audio_path = generate_tts_audio(text, language_hint)
        with open(audio_path, "rb") as audio_file:
            await update.message.reply_voice(
                voice=audio_file,
                caption=text[:1024],  # Telegram caption limit is 1024 chars
            )
    except Exception as e:
        logger.error(f"TTS failed, sending text-only fallback: {e}")
        # Fallback: send as text message reliably using effective_message or effective_chat
        if update.effective_message:
            await update.effective_message.reply_text(text)
        elif update.effective_chat:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
    finally:
        # Always delete temp file, even if sending fails
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)


async def send_voice_to_chat(bot, chat_id: int, audio_path: str) -> None:
    """
    Sends a pre-generated audio file to a specific chat_id.
    Used by the Flask webhook to notify patients after doctor confirmation.

    Args:
        bot: Telegram Bot instance
        chat_id: Patient's Telegram chat ID
        audio_path: Path to the .ogg audio file to send
    """
    try:
        with open(audio_path, "rb") as audio_file:
            await bot.send_voice(chat_id=chat_id, voice=audio_file)
        logger.info(f"Voice notification sent to chat_id: {chat_id}")
    except Exception as e:
        logger.error(f"Failed to send voice to chat {chat_id}: {e}")
    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)
