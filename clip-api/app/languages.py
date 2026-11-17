"""Languages: the ones the local Whisper models can transcribe, with their codes and English names.

The codes are the installed faster-whisper tokenizer's (`faster_whisper.tokenizer._LANGUAGE_CODES`); the names and
the order (most spoken first) are Whisper's own table. The table is written out here so the API does not have to
import the speech model to answer a request; `tests/test_languages.py` fails when it no longer matches the
installed tokenizer.

English is transcribed by the English-only models, as it always was. Every other language is transcribed by the
multilingual model of the same size (`multilingual_model`).
"""
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, WithJsonSchema

from .config import get_settings

LANGUAGES: dict[str, str] = {
    "en": "English", "zh": "Chinese", "de": "German", "es": "Spanish", "ru": "Russian", "ko": "Korean",
    "fr": "French", "ja": "Japanese", "pt": "Portuguese", "tr": "Turkish", "pl": "Polish", "ca": "Catalan",
    "nl": "Dutch", "ar": "Arabic", "sv": "Swedish", "it": "Italian", "id": "Indonesian", "hi": "Hindi",
    "fi": "Finnish", "vi": "Vietnamese", "he": "Hebrew", "uk": "Ukrainian", "el": "Greek", "ms": "Malay",
    "cs": "Czech", "ro": "Romanian", "da": "Danish", "hu": "Hungarian", "ta": "Tamil", "no": "Norwegian",
    "th": "Thai", "ur": "Urdu", "hr": "Croatian", "bg": "Bulgarian", "lt": "Lithuanian", "la": "Latin",
    "mi": "Maori", "ml": "Malayalam", "cy": "Welsh", "sk": "Slovak", "te": "Telugu", "fa": "Persian",
    "lv": "Latvian", "bn": "Bengali", "sr": "Serbian", "az": "Azerbaijani", "sl": "Slovenian", "kn": "Kannada",
    "et": "Estonian", "mk": "Macedonian", "br": "Breton", "eu": "Basque", "is": "Icelandic", "hy": "Armenian",
    "ne": "Nepali", "mn": "Mongolian", "bs": "Bosnian", "kk": "Kazakh", "sq": "Albanian", "sw": "Swahili",
    "gl": "Galician", "mr": "Marathi", "pa": "Punjabi", "si": "Sinhala", "km": "Khmer", "sn": "Shona",
    "yo": "Yoruba", "so": "Somali", "af": "Afrikaans", "oc": "Occitan", "ka": "Georgian", "be": "Belarusian",
    "tg": "Tajik", "sd": "Sindhi", "gu": "Gujarati", "am": "Amharic", "yi": "Yiddish", "lo": "Lao", "uz": "Uzbek",
    "fo": "Faroese", "ht": "Haitian Creole", "ps": "Pashto", "tk": "Turkmen", "nn": "Nynorsk", "mt": "Maltese",
    "sa": "Sanskrit", "lb": "Luxembourgish", "my": "Myanmar", "bo": "Tibetan", "tl": "Tagalog", "mg": "Malagasy",
    "as": "Assamese", "tt": "Tatar", "haw": "Hawaiian", "ln": "Lingala", "ha": "Hausa", "ba": "Bashkir",
    "jw": "Javanese", "su": "Sundanese", "yue": "Cantonese",
}
CODES: tuple[str, ...] = tuple(LANGUAGES)
# Only the large-v3 family has these among its language tokens: asking a smaller model for one fails. (Checked on
# this machine: the multilingual `base` model has no <|yue|> token.)
LARGE_V3_ONLY = frozenset({"yue"})


def name_of(code: str | None) -> str | None:
    """English name of a language code, or None for an unknown one."""
    return LANGUAGES.get(code or "")


def is_language(code) -> bool:
    return isinstance(code, str) and code in LANGUAGES


def normalise(value):
    """A code as it is stored: trimmed, lower case, without a region ("pt-BR" -> "pt"). A value that is not text,
    or that names no language even so, is handed back for the caller to reject."""
    if not isinstance(value, str):
        return value
    code = value.strip().lower().replace("_", "-")
    if code not in LANGUAGES and code.split("-")[0] in LANGUAGES:
        code = code.split("-")[0]
    return code


def multilingual_model(model: str) -> str:
    """The multilingual counterpart of a Whisper model name, same size: small.en -> small. A model that is already
    multilingual is its own counterpart, and "none" stays "none". The distilled models are English only."""
    name = (model or "none").strip()
    if name.lower() == "none":
        return "none"
    if name.startswith("distil-"):
        name = name[len("distil-"):]
        if name.startswith("large-v3"):
            return "large-v3"
    return name[:-3] if name.endswith(".en") else name


def transcribes(model: str, code: str) -> bool:
    """Whether this Whisper model can transcribe speech in this language."""
    if (model or "none").lower() == "none" or code not in LANGUAGES:
        return False
    if model.endswith(".en"):
        return code == "en"
    return code not in LARGE_V3_ONLY or "large-v3" in model or model in ("large", "turbo")


def caption_model() -> str:
    """The multilingual model used for clips and captions in a language other than English."""
    s = get_settings()
    return s.whisper_multilingual_model.strip() or multilingual_model(s.whisper_model)


def index_model() -> str:
    """The multilingual model used for whole-video transcripts in a language other than English."""
    s = get_settings()
    return s.whisper_index_multilingual_model.strip() or multilingual_model(s.whisper_index_model)


def source_languages() -> list[str]:
    """The codes `source_lang` accepts on this server. Every language in the table, less the few the configured
    multilingual models cannot transcribe. With transcription switched off nothing is transcribed at all, and the
    choice is only recorded."""
    models = [m for m in (caption_model(), index_model()) if m.lower() != "none"]
    return [c for c in CODES if c == "en" or all(transcribes(m, c) for m in models)]


def _known(value: str) -> str:
    if value not in LANGUAGES:
        raise ValueError(f"unknown language code '{value[:16]}'; GET /v1/languages lists the codes")
    return value


def _transcribable(value: str) -> str:
    if value not in source_languages():
        raise ValueError(f"{LANGUAGES[value]} ({value}) cannot be transcribed by the speech model on this server")
    return value


# Request fields. Both accept null; `source_lang: null` means "detect it", `target_lang: null` means "same as the
# source". The allowed codes are listed in the JSON schema, so GET /v1/options shows them.
_SCHEMA = WithJsonSchema({"type": "string", "enum": list(CODES)})
LanguageCode = Annotated[str, BeforeValidator(normalise), AfterValidator(_known), _SCHEMA]
SourceLanguage = Annotated[str, BeforeValidator(normalise), AfterValidator(_known), AfterValidator(_transcribable), _SCHEMA]
