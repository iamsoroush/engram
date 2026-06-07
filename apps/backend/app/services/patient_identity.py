import re
import unicodedata
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models import Patient

ARABIC_PERSIAN_TRANSLATION = str.maketrans(
    {
        "ك": "ک",
        "ي": "ی",
        "ى": "ی",
        "ئ": "ی",
        "ة": "ه",
        "ۀ": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
        "آ": "ا",
        "ٱ": "ا",
    }
)
DIGIT_TRANSLATION = str.maketrans(
    {
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
    }
)
PERSIAN_LATIN_TRANSLITERATION = {
    "ا": "a",
    "ب": "b",
    "پ": "p",
    "ت": "t",
    "ث": "s",
    "ج": "j",
    "چ": "ch",
    "ح": "h",
    "خ": "kh",
    "د": "d",
    "ذ": "z",
    "ر": "r",
    "ز": "z",
    "ژ": "zh",
    "س": "s",
    "ش": "sh",
    "ص": "s",
    "ض": "z",
    "ط": "t",
    "ظ": "z",
    "ع": "a",
    "غ": "gh",
    "ف": "f",
    "ق": "gh",
    "ک": "k",
    "گ": "g",
    "ل": "l",
    "م": "m",
    "ن": "n",
    "و": "v",
    "ه": "h",
    "ی": "i",
}
DETERMINISTIC_PATIENT_IDENTIFIER_TYPES = {
    "national_id",
    "phone",
    "email",
    "normalized_alias",
    "normalized_name",
    "birth_date",
}
DETERMINISTIC_IDENTIFIER_METADATA = {"generated_by": "patient-identity-normalization", "version": "2026-06-02"}


def normalize_digits(value: Any) -> str:
    """Return text with Persian, Arabic, and English digits represented as ASCII."""
    return str(value).translate(DIGIT_TRANSLATION)


def normalize_text_key(value: Any) -> str | None:
    """Normalize human-name/search text while preserving token boundaries."""
    if value is None:
        return None
    text = normalize_digits(value).translate(ARABIC_PERSIAN_TRANSLATION)
    text = text.replace("\u0640", "").replace("\u200c", " ")
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(character for character in decomposed if unicodedata.category(character) != "Mn")
    # Re-fold Arabic\u2192Persian after NFKD: compatibility decomposition turns Arabic presentation
    # forms (e.g. \ufef2 U+FEF2) and pre-decomposed input into base Arabic letters (\u064a/\u0643 \u2026) that the
    # pre-NFKD fold above could not reach, so without this they would never collapse onto their
    # Persian forms (\u06cc/\u06a9 \u2026). The map is idempotent and never touches Persian letters.
    folded = without_marks.translate(ARABIC_PERSIAN_TRANSLATION)
    lowered = folded.casefold().replace("_", " ")
    tokens = re.sub(r"[^\w\u0600-\u06ff]+", " ", lowered, flags=re.UNICODE)
    normalized = " ".join(tokens.split())
    return normalized or None


def normalize_identifier(value: Any) -> str:
    """Normalize a generic identifier or search value."""
    text = normalize_digits(value)
    digits = "".join(character for character in text if "0" <= character <= "9")
    return digits or (normalize_text_key(text) or "")


def normalize_national_id(value: Any) -> str | None:
    """Normalize national IDs to ASCII digits only."""
    if value is None:
        return None
    digits = "".join(character for character in normalize_digits(value) if "0" <= character <= "9")
    return digits or None


def normalize_email(value: Any) -> str | None:
    """Normalize email addresses for exact deterministic matching."""
    if value is None:
        return None
    email = normalize_digits(value).strip().casefold()
    return email or None


def normalize_iranian_phone(value: Any) -> str | None:
    """Normalize Iranian phone numbers to +98 form when the pattern is clear."""
    if value is None:
        return None
    digits = "".join(character for character in normalize_digits(value) if "0" <= character <= "9")
    if not digits:
        return None
    if digits.startswith("0098") and len(digits) >= 6:
        return "+98" + digits[4:]
    if digits.startswith("98") and len(digits) in {12, 13}:
        return "+" + digits
    if digits.startswith("0") and len(digits) == 11:
        return "+98" + digits[1:]
    if digits.startswith("9") and len(digits) == 10:
        return "+98" + digits
    return digits


def transliterate_persian_to_latin(value: Any) -> str | None:
    """Return a deterministic rough Latin search key for Persian-script aliases."""
    normalized = normalize_text_key(value)
    if not normalized:
        return None
    pieces: list[str] = []
    saw_persian = False
    for character in normalized:
        if character in PERSIAN_LATIN_TRANSLITERATION:
            saw_persian = True
            pieces.append(PERSIAN_LATIN_TRANSLITERATION[character])
        else:
            pieces.append(character)
    transliterated = re.sub(r"[^a-z0-9]+", " ", "".join(pieces).casefold())
    key = " ".join(transliterated.split())
    return key if saw_persian and key else None


def _compact_alias(value: str | None) -> str | None:
    if not value:
        return None
    compact = value.replace(" ", "")
    return compact if compact and compact != value else None


def normalized_aliases_for_value(value: Any) -> list[str]:
    """Return deterministic native and Latin alias keys for a staff or extracted name."""
    native = normalize_text_key(value)
    transliterated = transliterate_persian_to_latin(value)
    aliases = [native, transliterated, _compact_alias(native), _compact_alias(transliterated)]
    return list(dict.fromkeys(alias for alias in aliases if alias))


def patient_name_values(
    *,
    display_name: str | None,
    legal_first_name: str | None,
    legal_last_name: str | None,
) -> list[str]:
    """Return staff-entered name values that should receive search aliases."""
    values = [display_name, legal_first_name, legal_last_name]
    if legal_first_name and legal_last_name:
        values.append(f"{legal_first_name} {legal_last_name}")
    return [value.strip() for value in values if isinstance(value, str) and value.strip()]


def deterministic_identifier_specs(
    *,
    display_name: str,
    legal_first_name: str | None = None,
    legal_last_name: str | None = None,
    national_id: str | None = None,
    date_of_birth: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    source: str = "staff",
) -> list[dict[str, Any]]:
    """Build deterministic identifier rows without mutating staff-entered display fields."""
    specs: list[dict[str, Any]] = []

    if national_id and (normalized := normalize_national_id(national_id)):
        specs.append(
            {
                "identifier_type": "national_id",
                "identifier_value": national_id,
                "normalized_value": normalized,
                "source": source,
                "confidence": 1.0,
                "identifier_metadata": {**DETERMINISTIC_IDENTIFIER_METADATA, "kind": "exact_identifier"},
            }
        )
    if phone and (normalized := normalize_iranian_phone(phone)):
        specs.append(
            {
                "identifier_type": "phone",
                "identifier_value": phone,
                "normalized_value": normalized,
                "source": source,
                "confidence": 1.0,
                "identifier_metadata": {**DETERMINISTIC_IDENTIFIER_METADATA, "kind": "exact_contact"},
            }
        )
    if email and (normalized := normalize_email(email)):
        specs.append(
            {
                "identifier_type": "email",
                "identifier_value": email,
                "normalized_value": normalized,
                "source": source,
                "confidence": 1.0,
                "identifier_metadata": {**DETERMINISTIC_IDENTIFIER_METADATA, "kind": "exact_contact"},
            }
        )
    if date_of_birth:
        specs.append(
            {
                "identifier_type": "birth_date",
                "identifier_value": date_of_birth,
                "normalized_value": normalize_identifier(date_of_birth),
                "source": source,
                "confidence": 1.0,
                "identifier_metadata": {**DETERMINISTIC_IDENTIFIER_METADATA, "kind": "demographic"},
            }
        )

    aliases: list[tuple[str, str]] = []
    for value in patient_name_values(
        display_name=display_name,
        legal_first_name=legal_first_name,
        legal_last_name=legal_last_name,
    ):
        for alias in normalized_aliases_for_value(value):
            aliases.append((value, alias))
    for raw_value, alias in dict.fromkeys(aliases):
        specs.append(
            {
                "identifier_type": "normalized_alias",
                "identifier_value": raw_value,
                "normalized_value": alias,
                "source": source,
                "confidence": 0.92,
                "identifier_metadata": {**DETERMINISTIC_IDENTIFIER_METADATA, "kind": "name_alias"},
            }
        )

    display_alias = normalize_text_key(display_name)
    if display_alias:
        specs.append(
            {
                "identifier_type": "normalized_name",
                "identifier_value": display_name,
                "normalized_value": display_alias,
                "source": source,
                "confidence": 0.95,
                "identifier_metadata": {**DETERMINISTIC_IDENTIFIER_METADATA, "kind": "display_name"},
            }
        )

    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for spec in specs:
        normalized = spec.get("normalized_value")
        if normalized:
            deduped.setdefault((str(spec["identifier_type"]), str(normalized)), spec)
    return list(deduped.values())


def deterministic_identifier_specs_for_patient(
    patient: "Patient",
    *,
    national_id: str | None = None,
    source: str = "staff",
) -> list[dict[str, Any]]:
    """Build deterministic identifiers from a patient ORM object."""
    return deterministic_identifier_specs(
        display_name=patient.display_name,
        legal_first_name=patient.legal_first_name,
        legal_last_name=patient.legal_last_name,
        national_id=national_id,
        date_of_birth=patient.date_of_birth.isoformat() if patient.date_of_birth else None,
        phone=patient.phone,
        email=patient.email,
        source=source,
    )


def search_keys_for_query(query: str | None) -> list[str]:
    """Return normalized identifier keys worth searching for a user query."""
    if not query or not query.strip():
        return []
    keys = [
        normalize_text_key(query),
        transliterate_persian_to_latin(query),
        normalize_national_id(query),
        normalize_iranian_phone(query),
        normalize_email(query),
    ]
    aliases = normalized_aliases_for_value(query)
    return list(dict.fromkeys(key for key in [*keys, *aliases] if key))


def alias_tokens(values: Iterable[str]) -> list[str]:
    """Return searchable non-trivial tokens from normalized alias keys."""
    tokens: list[str] = []
    for value in values:
        tokens.extend(token for token in value.split() if len(token) >= 2)
    return list(dict.fromkeys(tokens))
