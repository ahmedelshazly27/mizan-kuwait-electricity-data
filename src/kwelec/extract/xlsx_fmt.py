"""What a spreadsheet cell shows, from its stored value and number format."""

import re
from decimal import ROUND_HALF_UP, Decimal

from ..normalize import stored_number

FMT = re.compile(r"^(#,##)?0(\.(0+))?$")


def displayed(value, number_format: str) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    d = stored_number(value)
    m = FMT.match(number_format or "")
    if not m:  # General and anything unusual: the stored number in full
        s = format(d, "f")
        return s.rstrip("0").rstrip(".") if "." in s else s
    places = len(m.group(3) or "")
    q = d.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return f"{q:,.{places}f}" if m.group(1) else f"{q:.{places}f}"
