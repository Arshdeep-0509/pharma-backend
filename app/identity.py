"""Login identifiers: developers sign in with a mobile number, admins and users with an email.

Both are stored in the same unique `users.username` column, normalised so the same person
can't end up with two spellings of one identifier.
"""

import re

from email_validator import EmailNotValidError, validate_email

_PHONE = re.compile(r"^[6-9]\d{9}$")  # Indian mobile number


def normalize_phone(value: str) -> str:
    """'+91 62835-31374', '06283531374' and '6283531374' all become '6283531374'."""
    digits = re.sub(r"[\s\-()]", "", value)
    if digits.startswith("+91"):
        digits = digits[3:]
    elif len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not _PHONE.fullmatch(digits):
        raise ValueError("Enter a valid 10-digit mobile number")
    return digits


def normalize_email(value: str) -> str:
    try:
        # No DNS lookup: works offline and doesn't leak addresses to resolvers.
        return validate_email(value.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        raise ValueError("Enter a valid email address")


def is_phone_identifier(value: str) -> bool:
    return "@" not in value
