"""
Validation & preprocessing logic.

Libyan National ID structure (12 digits):
  Position 1      : Gender  (1 = Male, 2 = Female)
  Positions 2-5   : Year of birth (4 digits, e.g. 1995)
  Positions 6-12  : Region + serial codes (not validated here)
"""

from datetime import date
import re


GENDER_DIGIT_MAP = {"1": "Male", "2": "Female"}


def is_valid_nid_format(nid: str) -> bool:
    """12 digits, numeric only."""
    return bool(nid) and bool(re.fullmatch(r"\d{12}", nid))


def derive_gender(nid: str) -> str | None:
    """Return 'Male' / 'Female' / None based on first digit."""
    if not is_valid_nid_format(nid):
        return None
    return GENDER_DIGIT_MAP.get(nid[0])


def derive_birth_year(nid: str) -> int | None:
    """Return the 4-digit birth year encoded in positions 2-5."""
    if not is_valid_nid_format(nid):
        return None
    try:
        return int(nid[1:5])
    except ValueError:
        return None


def verify_birthday(nid: str, birthday: date) -> bool:
    """
    Return True if the year encoded in the NID matches the entered birthday's year.
    A False here is a flag, not a hard error — the user may want to override.
    """
    nid_year = derive_birth_year(nid)
    if nid_year is None or birthday is None:
        return False
    return nid_year == birthday.year


def validate_student_form(data: dict) -> list[str]:
    """
    Run all compulsory-field and format checks.
    Returns a list of error strings; an empty list means OK.
    Birthday/NID year mismatch is NOT in this list — it's surfaced as a non-blocking flag.
    """
    errors = []

    if not data.get("full_name", "").strip():
        errors.append("Full name is required.")
    if not data.get("student_id", "").strip():
        errors.append("Student ID is required.")
    if not data.get("national_id", "").strip():
        errors.append("National ID is required.")
    if not data.get("birthday"):
        errors.append("Birthday is required.")
    if not data.get("country_abroad", "").strip():
        errors.append("Country of study abroad is required.")
    if not data.get("study_level", "").strip():
        errors.append("Study level is required.")
    if not data.get("study_field", "").strip():
        errors.append("Study field is required.")
    if not data.get("decision_no", "").strip():
        errors.append("Decision number is required.")

    nid = data.get("national_id", "")
    if nid and not is_valid_nid_format(nid):
        errors.append("National ID must be exactly 12 digits.")

    if data.get("email") and "@" not in data["email"]:
        errors.append("Email looks invalid.")

    sd, ed = data.get("start_date"), data.get("end_date")
    if sd and ed and ed < sd:
        errors.append("End date must be on or after start date.")

    return errors


def validate_accompaniment(data: dict) -> list[str]:
    """Same idea, lighter — for dependents."""
    errors = []
    if not data.get("full_name", "").strip():
        errors.append("Accompaniment name is required.")
    if not data.get("national_id", "").strip():
        errors.append("Accompaniment national ID is required.")
    elif not is_valid_nid_format(data["national_id"]):
        errors.append("Accompaniment national ID must be exactly 12 digits.")
    if not data.get("birthday"):
        errors.append("Accompaniment birthday is required.")
    if not data.get("relationship"):
        errors.append("Relationship is required.")
    return errors
