"""Formats a date as "Rates from [Month] [day][suffix] [year]", e.g.
"Rates from July 14th 2026".

Written by hand instead of relying on a date-formatting library because
most of them (including Python's own strftime) have no portable ordinal
suffix directive, and third-party ones vary in how they handle the 11th/
12th/13th exception.
"""

from datetime import date, datetime

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def ordinal_suffix(day: int) -> str:
    """Returns the English ordinal suffix for a day-of-month number.

    11th, 12th, 13th are exceptions to the usual 1st/2nd/3rd pattern
    (they take "th" even though they end in 1/2/3).
    """
    if 11 <= (day % 100) <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def format_ordinal_date(d: "date | datetime") -> str:
    """Formats a date as "[Month] [day][suffix] [year]", e.g. "July 14th 2026"."""
    month = MONTH_NAMES[d.month - 1]
    return f"{month} {d.day}{ordinal_suffix(d.day)} {d.year}"


def format_rate_date_stamp(d: "date | datetime") -> str:
    """Formats the full "Rates from ..." stamp used on the cover pages."""
    return f"Rates from {format_ordinal_date(d)}"


if __name__ == "__main__":
    # Quick manual sanity check across the tricky cases.
    for day in [1, 2, 3, 4, 11, 12, 13, 14, 21, 22, 23, 24, 30, 31]:
        d = date(2026, 7, day)
        print(format_rate_date_stamp(d))
