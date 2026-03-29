import os
import logging
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "hi")

# Initialise OpenAI client once at module level.
# The Whisper model runs REMOTELY — nothing is downloaded locally.
_openai_client = None


def get_client() -> OpenAI:
    """Lazy-initialise and return the OpenAI client."""
    global _openai_client
    if _openai_client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not set in .env. "
                "Get a key at https://platform.openai.com/api-keys"
            )
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
        logger.info("OpenAI client initialised for Whisper STT.")
    return _openai_client


def transcribe_audio(oga_path: str, wav_path: str = None) -> str:
    """
    Transcribes a Telegram voice file (.oga / Opus) using the OpenAI Whisper API.

    The .oga file is sent DIRECTLY to the API — no local conversion to WAV needed.
    The wav_path parameter is accepted for interface compatibility but is NOT used.

    Args:
        oga_path: Path to the downloaded .oga file from Telegram.
        wav_path: Ignored. Kept for interface compatibility only.

    Returns:
        Transcribed text as a string.

    Raises:
        RuntimeError: If OPENAI_API_KEY is not set or transcription returns empty.
        openai.OpenAIError: On API call failure (network, auth, quota, etc.).
    """
    client = get_client()

    logger.info(f"Sending audio to OpenAI Whisper API: {oga_path}")

    with open(oga_path, "rb") as audio_file:
        response = client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=audio_file,
            language=WHISPER_LANGUAGE,   # BCP-47 hint — improves accuracy for Hindi
            response_format="text",      # Returns plain string directly
        )

    # When response_format="text", response is the transcription string directly
    text = response.strip() if isinstance(response, str) else str(response).strip()

    if not text:
        raise RuntimeError("OpenAI Whisper API returned empty transcription.")

    logger.info(f"Transcription result: '{text}'")
    return text
