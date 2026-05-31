"""
Location text utilities for consistent city naming across the platform.
"""
from typing import Optional


def normalize_city_name(city: Optional[str]) -> Optional[str]:
    """
    Normalize a city name to Title Case with collapsed whitespace.

    Examples:
        "ranchi" -> "Ranchi"
        " RANCHI " -> "Ranchi"
        "new delhi" -> "New Delhi"
    """
    if city is None:
        return None

    cleaned = " ".join(str(city).strip().split())
    if not cleaned:
        return None

    return cleaned.title()


def city_key(city: Optional[str]) -> str:
    """Lowercase key for deduplication and case-insensitive comparison."""
    normalized = normalize_city_name(city)
    return normalized.lower() if normalized else ""


def cities_match(city_a: Optional[str], city_b: Optional[str]) -> bool:
    """Return True when two city names refer to the same place (case-insensitive)."""
    return city_key(city_a) == city_key(city_b) and bool(city_key(city_a))
