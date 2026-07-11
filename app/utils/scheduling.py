"""
Booking slot scheduling helpers.

Single source of truth for:
  - what "now" means for booking purposes (India / IST — the platform is
    India-only, see auth notes),
  - which day a salon is open/closed,
  - that day's opening/closing window,
  - generating bookable time slots (future-only, 30-min grid).

Both the public `/available-slots` endpoint and the booking-creation guard
use these helpers so the UI and the server enforce identical rules.
"""

from __future__ import annotations

import logging
from datetime import date as date_cls, datetime, time as time_cls, timedelta
from typing import Any, Dict, List, Optional, Tuple

try:  # Python 3.9+
    from zoneinfo import ZoneInfo
    _IST = ZoneInfo("Asia/Kolkata")
except Exception:  # pragma: no cover - fallback if tzdata unavailable
    from datetime import timezone
    _IST = timezone(timedelta(hours=5, minutes=30))

logger = logging.getLogger(__name__)

# Interval between consecutive bookable slots.
SLOT_INTERVAL_MINUTES = 30
# Minimum lead time from "now" before a slot is offered (0 = any future slot).
SLOT_MIN_LEAD_MINUTES = 0

_DEFAULT_OPEN = time_cls(9, 0)
_DEFAULT_CLOSE = time_cls(18, 0)

_DISPLAY_FMT = "%I:%M %p"      # e.g. "02:30 PM" (what the apps render/send back)
_DB_TIME_FMT = "%H:%M:%S"      # e.g. "14:30:00" (bookings.time_slots storage)


def now_ist() -> datetime:
    """Current wall-clock time in India (naive, IST)."""
    return datetime.now(_IST).replace(tzinfo=None)


def parse_date(date_str: str) -> date_cls:
    """Parse a YYYY-MM-DD date string."""
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def _parse_time(value: str) -> Optional[time_cls]:
    """Parse a time from either DB (HH:MM:SS / HH:MM) or display (h:MM AM/PM)."""
    if not value:
        return None
    v = value.strip()
    for fmt in (_DB_TIME_FMT, "%H:%M", _DISPLAY_FMT, "%I:%M%p"):
        try:
            return datetime.strptime(v.upper() if "%p" in fmt.lower() else v, fmt).time()
        except ValueError:
            continue
    return None


def parse_slot_time(value: str) -> Optional[time_cls]:
    """Parse a client-supplied slot string in either display or DB form."""
    return _parse_time(value)


def _day_hours_from_business_hours(
    business_hours: Any, day_name: str
) -> Optional[Tuple[Optional[time_cls], Optional[time_cls]]]:
    """
    Resolve a single day's hours from the salons.business_hours JSONB.

    Returns:
        None  -> business_hours has no entry for this day (caller should fall back)
        (None, None) -> explicitly Closed that day
        (open, close) -> parsed window
    """
    if not isinstance(business_hours, dict):
        return None
    raw = business_hours.get(day_name) or business_hours.get(day_name.title())
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text.lower() == "closed":
        return (None, None)
    # Expected "9:00 AM - 6:00 PM"
    parts = text.replace("–", "-").split("-")
    if len(parts) != 2:
        logger.warning("Unparsable business_hours for %s: %r", day_name, raw)
        return None
    open_t = _parse_time(parts[0])
    close_t = _parse_time(parts[1])
    if open_t is None or close_t is None:
        logger.warning("Unparsable business_hours times for %s: %r", day_name, raw)
        return None
    return (open_t, close_t)


def resolve_day_window(
    salon: Dict[str, Any], on_date: date_cls
) -> Tuple[bool, Optional[time_cls], Optional[time_cls]]:
    """
    Determine whether the salon is open on `on_date` and its hours.

    Precedence:
      1. business_hours JSONB (per-day; can mark a day "Closed" or set custom hours)
      2. working_days array (which weekdays the salon operates)
      3. opening_time / closing_time columns (or 9-6 default)

    Returns:
        (is_open, opening_time, closing_time)
    """
    day_name = on_date.strftime("%A").lower()  # e.g. "monday"

    # 1. Per-day business hours (authoritative when present)
    bh = _day_hours_from_business_hours(salon.get("business_hours"), day_name)
    if bh is not None:
        open_t, close_t = bh
        if open_t is None or close_t is None:
            return (False, None, None)  # explicitly Closed
        return (True, open_t, close_t)

    # 2. working_days list controls which weekdays are open
    working_days = salon.get("working_days")
    if working_days:
        normalized = {str(d).strip().lower() for d in working_days}
        if day_name not in normalized:
            return (False, None, None)

    # 3. Fall back to salon-wide opening/closing columns
    open_t = _parse_time(salon.get("opening_time") or "") or _DEFAULT_OPEN
    close_t = _parse_time(salon.get("closing_time") or "") or _DEFAULT_CLOSE
    return (True, open_t, close_t)


def generate_slots(
    salon: Dict[str, Any],
    on_date: date_cls,
    total_duration_minutes: int,
    existing_bookings: Optional[List[Dict[str, Any]]] = None,
    now: Optional[datetime] = None,
) -> List[str]:
    """
    Generate bookable slot strings ("%I:%M %p") for a salon on a given date.

    Rules enforced here (identical for every caller):
      - past dates yield no slots,
      - a closed day yields no slots,
      - slots stay within the day's open/close window and fit the service duration,
      - on the current day, only slots strictly in the future (+ lead time) are offered,
      - slots overlapping a non-cancelled existing booking are dropped.
    """
    now = now or now_ist()
    today = now.date()

    if on_date < today:
        return []

    is_open, opening, closing = resolve_day_window(salon, on_date)
    if not is_open or opening is None or closing is None:
        return []

    duration = total_duration_minutes if total_duration_minutes > 0 else 60
    existing_bookings = existing_bookings or []

    earliest = None
    if on_date == today:
        earliest = now + timedelta(minutes=SLOT_MIN_LEAD_MINUTES)

    # Precompute existing booking intervals for the day (defensive parsing).
    busy: List[Tuple[datetime, datetime]] = []
    for booking in existing_bookings:
        raw_slots = booking.get("time_slots") or []
        if not isinstance(raw_slots, list):
            continue
        b_duration = booking.get("duration_minutes") or duration
        for raw in raw_slots:
            t = _parse_time(str(raw))
            if t is None:
                continue
            b_start = datetime.combine(on_date, t)
            busy.append((b_start, b_start + timedelta(minutes=b_duration)))

    slots: List[str] = []
    current = datetime.combine(on_date, opening)
    closing_dt = datetime.combine(on_date, closing)

    while current + timedelta(minutes=duration) <= closing_dt:
        slot_end = current + timedelta(minutes=duration)

        # Future-only on the current day.
        if earliest is not None and current <= earliest:
            current += timedelta(minutes=SLOT_INTERVAL_MINUTES)
            continue

        # Skip slots that overlap an existing booking.
        if any(current < b_end and slot_end > b_start for b_start, b_end in busy):
            current += timedelta(minutes=SLOT_INTERVAL_MINUTES)
            continue

        slots.append(current.strftime(_DISPLAY_FMT))
        current += timedelta(minutes=SLOT_INTERVAL_MINUTES)

    return slots


def is_slot_bookable(
    salon: Dict[str, Any],
    on_date: date_cls,
    slot_str: str,
    now: Optional[datetime] = None,
) -> Tuple[bool, str]:
    """
    Server-side guard for booking creation: validate a single requested slot
    against date/closed-day/past-time rules.

    Returns (ok, reason). `reason` is a human-readable message when not ok.
    """
    now = now or now_ist()
    today = now.date()

    if on_date < today:
        return (False, "Cannot book for a past date.")

    is_open, opening, closing = resolve_day_window(salon, on_date)
    if not is_open or opening is None or closing is None:
        return (False, "The salon is closed on the selected day.")

    t = parse_slot_time(slot_str)
    if t is None:
        return (False, f"Invalid time slot: {slot_str!r}.")

    if not (opening <= t <= closing):
        return (False, "Selected time is outside the salon's working hours.")

    if on_date == today:
        slot_dt = datetime.combine(on_date, t)
        if slot_dt <= now + timedelta(minutes=SLOT_MIN_LEAD_MINUTES):
            return (False, "Cannot book a time slot in the past.")

    return (True, "")
