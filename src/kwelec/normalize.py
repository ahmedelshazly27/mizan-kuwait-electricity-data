"""Turning a printed cell into (value, status). Never estimates: anything that is not
a plain number as printed becomes null, with the printed string kept."""

import re
from decimal import Decimal, InvalidOperation

# Bidi controls the MEW PDFs wrap around numbers, plus no-break and zero-width spaces.
INVISIBLE = re.compile("[‎‏‪-‮⁦-⁩؜​ ﻿]")
DASHES = {"-", "–", "—", "‐", "−", "--", "---", "_"}  # MEW also prints "_" for an empty cell
EASTERN = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
NUMBER = re.compile(r"^\(?[+-]?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?\)?$")


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", INVISIBLE.sub("", s)).strip()


def parse_printed(printed: str) -> tuple[Decimal | None, str]:
    """Return (value, status) for a printed string.
    status: number | dash | blank | text (anything else, kept but not read as a number)."""
    s = clean(printed)
    if s == "":
        return None, "blank"
    if s in DASHES:
        return None, "dash"
    t = s.translate(EASTERN)
    if NUMBER.match(t):
        neg = t.startswith("(") and t.endswith(")")
        t = t.strip("()").replace(",", "")
        try:
            v = Decimal(t)
        except InvalidOperation:
            return None, "text"
        return (-v if neg else v), "number"
    return None, "text"


def stored_number(v: int | float) -> Decimal:
    """A spreadsheet cell's stored number, to the 15 significant digits a spreadsheet
    keeps (so 5491657.0600000005 is the 5491657.06 the cell holds)."""
    return Decimal(v) if isinstance(v, int) else Decimal(f"{v:.15g}")
