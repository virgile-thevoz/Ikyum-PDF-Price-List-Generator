"""Formats the "[Rates from|Tarifs...|Preise...] [date]" stamp shown on the
cover and back-cover pages, localized to match the client's language choice
(see i18n.py -- SUPPORTED_LANGS/DEFAULT_LANG -- and app.py's current_lang(),
which is what actually threads the chosen lang through to build_pricelist.py
and then here).

Deliberately hand-rolled rather than delegated to a date-formatting library:
most (including Python's own strftime) have no portable ordinal-suffix
directive, and the three languages handled here don't even agree on whether
ordinals are used at all -- English needs one on every day (1st/2nd/3rd/
4th/.../11th-13th/21st/...), French only on the 1st ("1er", otherwise a
plain cardinal number), and German not at all (just "21." with a period).
"""

from datetime import date, datetime

MONTH_NAMES = {
    "en": [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ],
    "fr": [
        "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre",
    ],
    "de": [
        "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember",
    ],
}

RATE_STAMP_LABELS = {
    "en": "Rates from",
    "fr": "Tarifs valables à partir du",
    "de": "Preise gültig ab",
}

DEFAULT_LANG = "en"


def ordinal_suffix(day: int) -> str:
    """Returns the English ordinal suffix for a day-of-month number.

    11th, 12th, 13th are exceptions to the usual 1st/2nd/3rd pattern
    (they take "th" even though they end in 1/2/3).
    """
    if 11 <= (day % 100) <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def format_ordinal_date(d: "date | datetime", lang: str = DEFAULT_LANG) -> str:
    """Formats a date the way each language actually writes it:

    - en: "July 14th 2026" (ordinal suffix on every day)
    - fr: "14 juillet 2026" (cardinal number, lowercase month -- except the
      1st of the month, written "1er")
    - de: "14. Juli 2026" (day followed by a period, capitalized month)
    """
    months = MONTH_NAMES.get(lang, MONTH_NAMES[DEFAULT_LANG])
    month = months[d.month - 1]
    if lang == "fr":
        day = "1er" if d.day == 1 else str(d.day)
        return f"{day} {month} {d.year}"
    if lang == "de":
        return f"{d.day}. {month} {d.year}"
    return f"{month} {d.day}{ordinal_suffix(d.day)} {d.year}"


def format_rate_date_stamp(d: "date | datetime", lang: str = DEFAULT_LANG) -> str:
    """Formats the full "Rates from ..." stamp used on the cover pages,
    localized to `lang` (falls back to English for an unsupported code)."""
    label = RATE_STAMP_LABELS.get(lang, RATE_STAMP_LABELS[DEFAULT_LANG])
    return f"{label} {format_ordinal_date(d, lang)}"


if __name__ == "__main__":
    # Quick manual sanity check across the tricky cases, all three languages.
    for lang in ("en", "fr", "de"):
        print(f"-- {lang} --")
        for day in [1, 2, 3, 4, 11, 12, 13, 14, 21, 22, 23, 24, 30, 31]:
            d = date(2026, 7, day)
            print(format_rate_date_stamp(d, lang))
