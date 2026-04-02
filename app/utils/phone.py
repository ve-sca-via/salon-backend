"""
Phone number utilities for validation and normalization to E.164 format
E.164 format: +[country_code][phone_number] (e.g., +918791464313)
"""
import re
from typing import Optional, Tuple


def normalize_phone(phone: Optional[str], country_code: str = "91") -> Optional[str]:
    """
    Normalize phone number to E.164 format (+country_code + phone)

    Args:
        phone: Phone number in various formats (with/without +, spaces, dashes, etc.)
        country_code: Default country code (default: 91 for India)

    Returns:
        Phone in E.164 format (e.g., +918791464313) or None if invalid

    Examples:
        normalize_phone("8791464313") -> "+918791464313"
        normalize_phone("+918791464313") -> "+918791464313"
        normalize_phone("91 8791464313") -> "+918791464313"
        normalize_phone("") -> None
    """
    if not phone:
        return None

    # Strip whitespace and convert to string
    phone = str(phone).strip()

    if not phone:
        return None

    # Remove common formatting characters
    phone = phone.replace("+", "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")

    # Check if phone starts with country code digits (but not full)
    if phone.startswith(country_code):
        # Remove country code prefix (e.g., "918791464313" -> "8791464313")
        phone = phone[len(country_code):]

    # Remove any non-digit characters
    phone = re.sub(r"\D", "", phone)

    if not phone:
        return None

    # For India, phone should be 10 digits
    # For other countries, adjust as needed
    if country_code == "91" and len(phone) != 10:
        return None  # Invalid Indian phone number

    # Build E.164 format
    return f"+{country_code}{phone}"


def is_phone_valid_e164(phone: Optional[str]) -> bool:
    """
    Check if phone number is in valid E.164 format

    Args:
        phone: Phone number to validate

    Returns:
        True if valid E.164 format, False otherwise
    """
    if not phone:
        return False

    # E.164 format: + followed by 1-15 digits
    pattern = r"^\+[1-9]\d{1,14}$"
    return bool(re.match(pattern, str(phone)))


def extract_country_code_and_phone(phone: str) -> Tuple[str, str]:
    """
    Extract country code and phone number from E.164 or mixed format

    Args:
        phone: Phone number in E.164 or other format

    Returns:
        Tuple of (country_code, phone_number) without +

    Example:
        extract_country_code_and_phone("+918791464313") -> ("91", "8791464313")
    """
    phone = str(phone).replace("+", "").strip()

    if not phone or not phone.isdigit():
        return "91", phone  # Default to India

    # Country code is 1-3 digits, usually 1-2 for most countries
    # Common: 91 (India), 1 (US/Canada), 44 (UK), 33 (France), etc.
    for cc_len in [3, 2, 1]:
        potential_cc = phone[:cc_len]
        remaining = phone[cc_len:]

        # For India (91), phone should be 10 digits
        if potential_cc == "91" and len(remaining) == 10:
            return potential_cc, remaining

        # For other common country codes, be more lenient
        if len(remaining) >= 7:  # Most phones are at least 7 digits
            return potential_cc, remaining

    # Default: assume 91 (India)
    return "91", phone


def mask_phone(phone: Optional[str]) -> Optional[str]:
    """
    Mask phone number for display (show only last 4 digits)
    Useful for logs and responses

    Args:
        phone: Phone number to mask

    Returns:
        Masked phone (e.g., "+91****4313") or None

    Example:
        mask_phone("+918791464313") -> "+91****4313"
    """
    if not phone:
        return None

    phone = str(phone)
    if len(phone) <= 4:
        return "*" * len(phone)

    last_4 = phone[-4:]
    masked = "*" * (len(phone) - 4)
    return masked + last_4
