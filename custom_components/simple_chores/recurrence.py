"""Recurrence calculation logic for the Simple Chores integration.

Pure date math functions for calculating next due dates based on
interval-based and anchored recurrence patterns.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

from dateutil.relativedelta import relativedelta

from .const import (
    ANCHOR_DAY_OF_MONTH,
    ANCHOR_WEEK_PATTERN,
    FREQUENCY_BIANNUAL,
    FREQUENCY_BIMONTHLY,
    FREQUENCY_BIWEEKLY,
    FREQUENCY_DAILY,
    FREQUENCY_MONTHLY,
    FREQUENCY_ONCE,
    FREQUENCY_QUARTERLY,
    FREQUENCY_WEEKLY,
    FREQUENCY_YEARLY,
    RECURRENCE_ANCHORED,
    RECURRENCE_INTERVAL,
    WEEK_LAST,
    WINDOWED_FREQUENCIES,
)

# Length in months of each windowed frequency's calendar window.
_WINDOW_MONTHS: dict[str, int] = {
    FREQUENCY_QUARTERLY: 3,
    FREQUENCY_BIANNUAL: 6,
    FREQUENCY_YEARLY: 12,
}


def is_windowed_frequency(frequency: str) -> bool:
    """Return True if the frequency uses static calendar-aligned windows.

    Quarterly, biannual, and yearly chores are tracked by a completion window
    rather than a single sliding due date.
    """
    return frequency in WINDOWED_FREQUENCIES


def get_calendar_window(d: date, frequency: str) -> tuple[date, date]:
    """Return the (start, end) of the fixed calendar window containing ``d``.

    Windows are aligned to the calendar, independent of any completion date:
      - quarterly: Jan-Mar / Apr-Jun / Jul-Sep / Oct-Dec
      - biannual:  Jan-Jun / Jul-Dec
      - yearly:    full calendar year

    The end date is inclusive (the last day of the window).
    """
    months = _WINDOW_MONTHS.get(frequency)
    if months is None:
        raise ValueError(f"{frequency!r} is not a windowed frequency")

    # Index of the window within the year (0-based), then its starting month.
    window_index = (d.month - 1) // months
    start_month = window_index * months + 1
    start = date(d.year, start_month, 1)
    end = start + relativedelta(months=months) - timedelta(days=1)
    return start, end


def get_next_window(current_end: date, frequency: str, today: date) -> tuple[date, date]:
    """Return the next consecutive calendar window after ``current_end``.

    Advances forward only as far as needed so the returned window's end is on or
    after ``today``. A normal in-window completion lands on the immediately
    following window, while a very overdue completion skips windows that are
    already entirely in the past.
    """
    # The window starting the day after the current one ends.
    start, end = get_calendar_window(current_end + timedelta(days=1), frequency)
    while end < today:
        start, end = get_calendar_window(end + timedelta(days=1), frequency)
    return start, end


def initial_window(
    start_date: date | None, today: date, frequency: str
) -> tuple[date, date]:
    """Return the starting window for a newly created windowed chore.

    Uses the window containing ``start_date`` (or ``today`` if not given),
    advanced forward so the window has not already fully elapsed.
    """
    seed = start_date or today
    start, end = get_calendar_window(seed, frequency)
    while end < today:
        start, end = get_calendar_window(end + timedelta(days=1), frequency)
    return start, end


def iter_calendar_windows(
    frequency: str, range_start: date, range_end: date
) -> list[tuple[date, date]]:
    """Return all static calendar windows overlapping ``[range_start, range_end]``.

    Windows are calendar-aligned and consecutive (no skipping), so this is
    suitable for rendering a timeline of past/current/future windows.
    """
    if range_end < range_start:
        return []

    windows: list[tuple[date, date]] = []
    start, end = get_calendar_window(range_start, frequency)
    while start <= range_end:
        windows.append((start, end))
        start, end = get_calendar_window(end + timedelta(days=1), frequency)
    return windows


def calculate_next_due(from_date: date, frequency: str) -> date | None:
    """Calculate the next due date based on frequency.

    Returns None for one-off chores (frequency='once'), indicating they should not be rescheduled.
    """
    if frequency == FREQUENCY_ONCE:
        return None  # One-off chores don't get rescheduled
    if frequency == FREQUENCY_DAILY:
        return from_date + timedelta(days=1)
    if frequency == FREQUENCY_WEEKLY:
        return from_date + timedelta(weeks=1)
    if frequency == FREQUENCY_BIWEEKLY:
        return from_date + timedelta(weeks=2)
    if frequency == FREQUENCY_MONTHLY:
        return from_date + relativedelta(months=1)
    if frequency == FREQUENCY_BIMONTHLY:
        return from_date + relativedelta(months=2)
    if frequency == FREQUENCY_QUARTERLY:
        return from_date + relativedelta(months=3)
    if frequency == FREQUENCY_BIANNUAL:
        return from_date + relativedelta(months=6)
    if frequency == FREQUENCY_YEARLY:
        return from_date + relativedelta(years=1)
    return from_date


def get_week_bounds(for_date: date) -> tuple[date, date]:
    """Get the start (Sunday) and end (Saturday) of the week containing the given date."""
    # Python weekday: Monday=0, Sunday=6
    # We want Sunday=0, so adjust
    days_since_sunday = (for_date.weekday() + 1) % 7
    week_start = for_date - timedelta(days=days_since_sunday)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def get_nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date | None:
    """Get the nth occurrence of a weekday in a month.

    Args:
        year: The year
        month: The month (1-12)
        weekday: Day of week (0=Sunday, 6=Saturday) - Note: uses our Sunday=0 convention
        n: Which occurrence (1-4, or 5 for last)

    Returns:
        The date of the nth weekday, or None if it doesn't exist
    """
    # Convert our weekday (Sunday=0) to Python's weekday (Monday=0)
    python_weekday = (weekday - 1) % 7  # Sunday(0)->6, Monday(1)->0, etc.

    # Get first day of month and number of days in month
    first_day = date(year, month, 1)
    days_in_month = calendar.monthrange(year, month)[1]

    if n == WEEK_LAST:
        # Find last occurrence - start from end of month
        last_day = date(year, month, days_in_month)
        days_back = (last_day.weekday() - python_weekday) % 7
        result = last_day - timedelta(days=days_back)
        return result

    # Find first occurrence of this weekday
    days_ahead = (python_weekday - first_day.weekday()) % 7
    first_occurrence = first_day + timedelta(days=days_ahead)

    # Calculate nth occurrence
    result = first_occurrence + timedelta(weeks=n - 1)

    # Check if still in same month
    if result.month != month:
        return None

    return result


def calculate_next_anchored_weekly(
    from_date: date,
    anchor_days: list[int],
    interval: int = 1,
) -> date:
    """Calculate next due date for anchored weekly recurrence.

    Args:
        from_date: The date to calculate from (usually today or completion date)
        anchor_days: List of weekdays (0=Sunday, 6=Saturday)
        interval: Number of weeks between occurrences (default 1)

    Returns:
        The next due date
    """
    if not anchor_days:
        return from_date + timedelta(weeks=interval)

    # Sort anchor days
    sorted_days = sorted(anchor_days)

    # Get current day of week (convert Python's Monday=0 to our Sunday=0)
    current_dow = (from_date.weekday() + 1) % 7

    # Find next anchor day in current week
    for day in sorted_days:
        if day > current_dow:
            # Found a day later this week
            days_ahead = day - current_dow
            return from_date + timedelta(days=days_ahead)

    # No more days this week - go to first anchor day of next interval
    # Calculate days until next week's first anchor day
    first_anchor = sorted_days[0]
    days_until_sunday = (7 - current_dow) % 7 or 7  # Days until next Sunday
    days_from_sunday_to_anchor = first_anchor

    # If interval > 1, skip additional weeks
    extra_weeks = (interval - 1) * 7

    return from_date + timedelta(days=days_until_sunday + days_from_sunday_to_anchor + extra_weeks)


def calculate_next_anchored_monthly(
    from_date: date,
    anchor_type: str,
    anchor_day_of_month: int | None = None,
    anchor_week: int | None = None,
    anchor_weekday: int | None = None,
    months_interval: int = 1,
) -> date:
    """Calculate next due date for anchored monthly recurrence.

    Args:
        from_date: The date to calculate from
        anchor_type: 'day_of_month' or 'week_pattern'
        anchor_day_of_month: Day of month (1-31) for day_of_month type
        anchor_week: Week ordinal (1-5, 5=last) for week_pattern type
        anchor_weekday: Weekday (0-6, 0=Sunday) for week_pattern type
        months_interval: Number of months between occurrences

    Returns:
        The next due date
    """
    if anchor_type == ANCHOR_DAY_OF_MONTH:
        # Simple day of month (e.g., 15th of every month)
        target_day = anchor_day_of_month or 1

        # Try current month first
        year, month = from_date.year, from_date.month
        days_in_month = calendar.monthrange(year, month)[1]
        actual_day = min(target_day, days_in_month)
        target_date = date(year, month, actual_day)

        if target_date > from_date:
            return target_date

        # Move to next month interval
        next_month_date = from_date + relativedelta(months=months_interval)
        year, month = next_month_date.year, next_month_date.month
        days_in_month = calendar.monthrange(year, month)[1]
        actual_day = min(target_day, days_in_month)
        return date(year, month, actual_day)

    elif anchor_type == ANCHOR_WEEK_PATTERN:
        # Week pattern (e.g., 2nd Tuesday of every month)
        if anchor_week is None or anchor_weekday is None:
            return from_date + relativedelta(months=months_interval)

        # Try current month first
        year, month = from_date.year, from_date.month
        target_date = get_nth_weekday_of_month(year, month, anchor_weekday, anchor_week)

        if target_date and target_date > from_date:
            return target_date

        # Move to next month interval
        next_month_date = from_date + relativedelta(months=months_interval)
        year, month = next_month_date.year, next_month_date.month
        target_date = get_nth_weekday_of_month(year, month, anchor_weekday, anchor_week)

        # If pattern doesn't exist in target month (e.g., 5th Monday doesn't exist),
        # keep trying subsequent months
        attempts = 0
        while target_date is None and attempts < 12:
            next_month_date = next_month_date + relativedelta(months=1)
            year, month = next_month_date.year, next_month_date.month
            target_date = get_nth_weekday_of_month(year, month, anchor_weekday, anchor_week)
            attempts += 1

        return target_date or from_date + relativedelta(months=months_interval)

    return from_date + relativedelta(months=months_interval)


def calculate_next_due_for_chore(chore: dict[str, Any], from_date: date) -> date | None:
    """Calculate the next due date for a chore based on its recurrence settings.

    This is the main entry point for due date calculation that handles both
    interval-based and anchored recurrence.

    Args:
        chore: The chore dictionary with recurrence settings
        from_date: The date to calculate from (usually completion date)

    Returns:
        The next due date, or None for one-off chores
    """
    frequency = chore.get("frequency", FREQUENCY_WEEKLY)
    recurrence_type = chore.get("recurrence_type", RECURRENCE_INTERVAL)
    interval = chore.get("interval", 1)

    # One-off chores don't recur
    if frequency == FREQUENCY_ONCE:
        return None

    # Use interval-based calculation for backward compatibility
    if recurrence_type != RECURRENCE_ANCHORED:
        return calculate_next_due(from_date, frequency)

    # Anchored recurrence
    if frequency in (FREQUENCY_WEEKLY, FREQUENCY_BIWEEKLY):
        anchor_days = chore.get("anchor_days_of_week", [])
        week_interval = 2 if frequency == FREQUENCY_BIWEEKLY else interval
        return calculate_next_anchored_weekly(from_date, anchor_days, week_interval)

    elif frequency in (FREQUENCY_MONTHLY, FREQUENCY_BIMONTHLY, FREQUENCY_QUARTERLY, FREQUENCY_BIANNUAL):
        anchor_type = chore.get("anchor_type", ANCHOR_DAY_OF_MONTH)
        months_map = {
            FREQUENCY_MONTHLY: 1,
            FREQUENCY_BIMONTHLY: 2,
            FREQUENCY_QUARTERLY: 3,
            FREQUENCY_BIANNUAL: 6,
        }
        months_interval = months_map.get(frequency, 1) * interval
        return calculate_next_anchored_monthly(
            from_date,
            anchor_type,
            chore.get("anchor_day_of_month"),
            chore.get("anchor_week"),
            chore.get("anchor_weekday"),
            months_interval,
        )

    elif frequency == FREQUENCY_YEARLY:
        # For yearly, use the anchor month from the original due date
        # and apply the monthly anchor logic
        anchor_type = chore.get("anchor_type", ANCHOR_DAY_OF_MONTH)
        return calculate_next_anchored_monthly(
            from_date,
            anchor_type,
            chore.get("anchor_day_of_month"),
            chore.get("anchor_week"),
            chore.get("anchor_weekday"),
            12 * interval,  # 12 months = 1 year
        )

    # Fallback to interval-based
    return calculate_next_due(from_date, frequency)
