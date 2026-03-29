import re
import dateparser
import logging

logger = logging.getLogger(__name__)


class STATES:
    """Integer state identifiers for ConversationHandler."""
    ASK_NAME     = 0
    ASK_AGE      = 1
    ASK_PHONE    = 2
    ASK_DATE     = 3
    ASK_TIME     = 4
    ASK_SYMPTOMS = 5


# The canonical order of fields to collect
FIELD_ORDER = [
    STATES.ASK_NAME,
    STATES.ASK_AGE,
    STATES.ASK_PHONE,
    STATES.ASK_DATE,
    STATES.ASK_TIME,
    STATES.ASK_SYMPTOMS,
]


# Maps state integer to the user_data key where the answer is stored
STATE_TO_KEY = {
    STATES.ASK_NAME:     "patient_name",
    STATES.ASK_AGE:      "patient_age",
    STATES.ASK_PHONE:    "patient_phone",
    STATES.ASK_DATE:     "preferred_date",
    STATES.ASK_TIME:     "preferred_time",
    STATES.ASK_SYMPTOMS: "symptoms",
}


# Hindi voice prompts for each state
STATE_PROMPTS = {
    STATES.ASK_NAME: (
        "कृपया अपना पूरा नाम बताएं।"
    ),
    STATES.ASK_AGE: (
        "आपकी उम्र क्या है?"
    ),
    STATES.ASK_PHONE: (
        "आपका मोबाइल नंबर क्या है?"
    ),
    STATES.ASK_DATE: (
        "आप किस तारीख को अपॉइंटमेंट चाहते हैं? "
        "जैसे: पंद्रह अगस्त, या कल, या परसों।"
    ),
    STATES.ASK_TIME: (
        "आप किस समय आना चाहते हैं? "
        "जैसे: सुबह दस बजे, या दोपहर दो बजे।"
    ),
    STATES.ASK_SYMPTOMS: (
        "आपको क्या तकलीफ हो रही है? "
        "कृपया अपने लक्षण बताएं।"
    ),
}


def get_prompt_for_state(state: int) -> str:
    """Returns the Hindi voice prompt for the given state."""
    return STATE_PROMPTS.get(state, "कृपया जानकारी दें।")


def get_state_key(state: int) -> str:
    """Returns the user_data dictionary key for the given state."""
    return STATE_TO_KEY.get(state, "unknown")


def parse_date(raw: str) -> str:
    """
    Parses a date from natural language (Hindi or English).
    Uses the dateparser library with PREFER_DATES_FROM='future' setting.
    Returns date as "DD-MM-YYYY" string, or the raw string if parsing fails.

    Examples:
        "कल" → tomorrow's date in DD-MM-YYYY
        "15 August" → "15-08-2025"
        "परसों" → day after tomorrow
    """
    settings = {
        "PREFER_DATES_FROM": "future",
        "RETURN_AS_TIMEZONE_AWARE": False,
        "DATE_ORDER": "DMY",
    }
    parsed = dateparser.parse(raw, languages=["hi", "en"], settings=settings)
    if parsed:
        return parsed.strftime("%d-%m-%Y")
    return raw  # Return as-is if dateparser cannot parse


def parse_time(raw: str) -> str:
    """
    Parses a time from natural language.
    Uses dateparser. Returns "HH:MM" in 24h format, or raw if parsing fails.

    Examples:
        "सुबह दस बजे" → "10:00"
        "दोपहर दो बजे" → "14:00"
        "शाम पाँच बजे" → "17:00"
    """
    parsed = dateparser.parse(raw, languages=["hi", "en"])
    if parsed:
        return parsed.strftime("%H:%M")
    return raw


def parse_age(raw: str) -> str:
    """
    Extracts numeric age from a string.
    "मेरी उम्र 32 साल है" → "32"
    Falls back to returning the raw string.
    """
    numbers = re.findall(r'\d+', raw)
    if numbers:
        return numbers[0]
    return raw


def parse_phone(raw: str) -> str:
    """
    Extracts a 10-digit Indian mobile number from spoken text.
    Removes spaces, dashes, country code prefixes (+91, 0).
    """
    digits = re.sub(r'\D', '', raw)  # Remove all non-digits
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]  # Remove country code
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]  # Remove leading 0
    return digits
