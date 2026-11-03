"""Dates written into sentences. Every date a sentence shows is US format, MM/DD/YYYY, whoever wrote the sentence.

Code written messages call us(). Text from a model goes through us_text(), which turns an ISO date (YYYY-MM-DD) into the same
format. A date inside a quotation is left alone unless the quotation is only that date, because a quote from a document keeps
the document's own words."""

import re
from datetime import date

_ISO = re.compile(r"(?<![\d-])(\d{4})-(\d{2})-(\d{2})(?![\d-])")
_QUOTED = re.compile(r'"[^"\n]*"')
_ONLY_DATE = re.compile(r'^"\s*\d{4}-\d{2}-\d{2}\s*"$')


def us(value: date) -> str:
    """A date as MM/DD/YYYY."""
    return f"{value.month:02d}/{value.day:02d}/{value.year}"


def _convert(text: str) -> str:
    def swap(match: re.Match[str]) -> str:
        year, month, day = (int(g) for g in match.groups())
        try:
            return us(date(year, month, day))
        except ValueError:
            return match.group(0)  # not a real date, so it is not touched

    return _ISO.sub(swap, text)


def us_text(text: str) -> str:
    """The text with every ISO date outside a quotation written as MM/DD/YYYY. A quotation that is only a date is converted too."""
    out, last = [], 0
    for quoted in _QUOTED.finditer(text):
        out.append(_convert(text[last : quoted.start()]))
        out.append(_convert(quoted.group(0)) if _ONLY_DATE.match(quoted.group(0)) else quoted.group(0))
        last = quoted.end()
    out.append(_convert(text[last:]))
    return "".join(out)
