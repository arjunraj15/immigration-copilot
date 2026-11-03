"""Deterministic clean up of values. Names and identifiers stay exactly as written.

Only a trim, one space between words and a date turned into YYYY-MM-DD when the date reads one way only."""

import re
from datetime import date, datetime

DATE_FIELDS = ("date_of_birth", "passport_expiration", "last_entry_date", "employment_start_date")
_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_SLASH = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$")
_YMD = re.compile(r"^(\d{4})[/.](\d{1,2})[/.](\d{1,2})$")
# A note may hedge a date ("about 2024-05-07", "start maybe 2024-05-07"). The date is the same date, so the hedge is dropped for the comparison.
_HEDGE = re.compile(r"^(?:about|around|approximately|approx\.?|circa|roughly|maybe|~)\s+", re.I)
_ORDINAL = re.compile(r"(?<=\d)(st|nd|rd|th)\b", re.I)
_WORDS = ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y", "%b. %d, %Y", "%d %B, %Y", "%d %b, %Y",
          "%d-%b-%Y", "%d-%B-%Y", "%d %b. %Y")


def tidy(value: str) -> str:
    return " ".join(str(value).split())


def _make(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _slash(match: re.Match[str]) -> date | None:
    """US order is month first. A date such as 03/04/2025 could also be day first, so it is left alone."""
    first, second, year = (int(g) for g in match.groups())
    if first == second or first > 12 >= second:
        month, day = (first, second) if first <= 12 else (second, first)
        return _make(year, month, day)
    if second > 12 >= first:
        return _make(year, first, second)
    return None


def parse_date(value: str) -> date | None:
    """The date when the text reads as one date only, else None."""
    text = _ORDINAL.sub("", _HEDGE.sub("", tidy(value))).replace("Sept", "Sep").replace("sept", "sep")
    if match := _ISO.match(text) or _YMD.match(text):
        return _make(*(int(g) for g in match.groups()))
    if match := _SLASH.match(text):
        return _slash(match)
    for pattern in _WORDS:
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def normalize(field: str, value: str, date_fields: tuple[str, ...] = DATE_FIELDS) -> str:
    """The stored normalized value. A date field becomes ISO when it can, everything else is only tidied."""
    text = tidy(value)
    if field in date_fields and (parsed := parse_date(text)) is not None:
        return parsed.isoformat()
    return text


def compare_key(normalized: str) -> str:
    """Used only to compare two values. It ignores letter case and spacing and is never shown."""
    return tidy(normalized).casefold()
