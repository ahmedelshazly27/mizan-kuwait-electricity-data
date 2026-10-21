"""UNdata Energy Statistics (EDATA), Kuwait electricity. The site's download link
and its pager handler both fail, but a query filtered to one transaction fits on one
page (at most 50 rows), so the page lists the transactions and each is read on its
own. Every page is kept as retrieved."""

import html
import re

import requests

BASE = "https://data.un.org/Data.aspx"
FILTER = "cmID:EL;crID:414"
UA = {"User-Agent": "mizan-kuwait-electricity-data (+https://github.com/ahmedelshazly27/mizan-kuwait-electricity-data)"}
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
PAGE_SIZE = 50


def _get(session: requests.Session, flt: str) -> str:
    # The filter's ':' and ';' must reach the server unencoded.
    r = session.get(f"{BASE}?d=EDATA&f={flt}", headers=UA, timeout=120)
    r.raise_for_status()
    return r.text


def _rows(page: str) -> list[list[str]]:
    out = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).replace("\xa0", " ").strip() for c in CELL.findall(r)]
        if len(cells) >= 5 and cells[0] == "Kuwait":
            out.append(cells[:6] + [""] * (6 - len(cells[:6])))
    return out


def transactions(page: str) -> list[tuple[str, str]]:
    found = re.findall(r'value="trID%3a([0-9a-z]+)" name="([^"]+)"', page)
    return list(dict.fromkeys((t, html.unescape(n)) for t, n in found))


def footnotes(page: str) -> str:
    m = re.search(r"Footnotes(.*?)Source", re.sub(r"<[^>]+>", " ", page), re.S)
    return re.sub(r"\s+", " ", html.unescape(m.group(1))).strip() if m else ""


def fetch(session: requests.Session) -> tuple[dict[str, str], list[list[str]], str]:
    """(raw pages by transaction id, rows [country, transaction, year, unit, quantity, footnote], footnotes)."""
    index = _get(session, FILTER)
    pages, rows, notes = {"index": index}, [], footnotes(index)
    for tid, name in transactions(index):
        page = _get(session, f"{FILTER};trID:{tid}")
        got = _rows(page)
        if len(got) >= PAGE_SIZE:
            raise RuntimeError(f"UNdata {name}: {len(got)} rows, more than one page")
        if any(r[1] != name for r in got):
            raise RuntimeError(f"UNdata {name}: rows for another transaction")
        pages[tid] = page
        rows += got
        notes = notes or footnotes(page)
    return pages, rows, notes
