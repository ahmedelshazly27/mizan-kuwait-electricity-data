"""CSB downloads are ASP.NET postbacks with no static URLs, and row numbers shift
as editions are added. So the listing is read on every run and the row is found
by its year column, never by position."""

import html
import re
from dataclasses import dataclass

import requests

BASE = "https://www.csb.gov.kw/Pages/Statistics"
UA = {"User-Agent": "mizan-kuwait-electricity-data (+https://github.com/ahmedelshazly27/mizan-kuwait-electricity-data)"}

ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
TARGET = re.compile(r"__doPostBack\(&#39;([^&]+)&#39;")


@dataclass
class Row:
    title: str
    year: str
    pdf_target: str | None
    xls_target: str | None


def _text(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def listing(session: requests.Session, page_id: int, parent: int) -> tuple[str, list[Row]]:
    r = session.get(BASE, params={"ID": page_id, "ParentCatID": parent}, headers=UA, timeout=120)
    r.raise_for_status()
    rows = []
    for m in ROW.finditer(r.text):
        cells = CELL.findall(m.group(1))
        if len(cells) < 4 or "__doPostBack" not in cells[1]:
            continue
        targets = TARGET.findall(cells[1])
        pdf = next((t for t in targets if t.endswith("LinkButton3")), None) if "pdf_icon" in cells[1] else None
        xls = next((t for t in targets if t.endswith("LinkButton4")), None) if "icon_xls" in cells[1] else None
        rows.append(Row(_text(cells[0]), _text(cells[3]), pdf, xls))
    return r.text, rows


def _form(page: str) -> dict[str, str]:
    """Every hidden and text input on the page, as the browser would post it."""
    form = {}
    for tag in re.findall(r"<input[^>]+>", page):
        n, v, t = (re.search(rf'{a}="([^"]*)"', tag) for a in ("name", "value", "type"))
        if n and (not t or t.group(1) in ("hidden", "text")):
            form[html.unescape(n.group(1))] = html.unescape(v.group(1)) if v else ""
    return form


def _postback(session: requests.Session, page_id: int, parent: int, page: str, target: str) -> requests.Response:
    form = _form(page)
    form.update({"__EVENTTARGET": target, "__EVENTARGUMENT": ""})
    r = session.post(f"{BASE}?ID={page_id}&ParentCatID={parent}", data=form, headers=UA, timeout=300)
    r.raise_for_status()
    return r


def _child_rows(page: str) -> list[Row]:
    i = page.find("RepeaterForChild")
    if i < 0:
        return []
    rows = []
    for m in ROW.finditer(page[page.rfind("<tbody", 0, i):]):
        cells = CELL.findall(m.group(1))
        if len(cells) < 4 or "RepeaterForChild" not in cells[1]:
            continue
        targets = TARGET.findall(cells[1])
        pdf = next((t for t in targets if t.endswith("LinkButton3")), None)
        xls = next((t for t in targets if t.endswith("LinkButton4")), None)
        rows.append(Row(_text(cells[0]), _text(cells[3]), pdf, xls))
    return rows


def download(session: requests.Session, page_id: int, parent: int, year: str, chapter: str) -> tuple[bytes, str, str]:
    """Return (content, filename as served, chapter title) for the edition whose year
    column equals `year` and the chapter workbook whose title matches `chapter` (regex).
    An edition's Excel link opens a second listing of chapter workbooks."""
    page, rows = listing(session, page_id, parent)
    match = [r for r in rows if r.year == year]
    if len(match) != 1 or not match[0].xls_target:
        raise LookupError(f"CSB page {page_id}: {len(match)} rows with year {year!r} and an Excel link")
    child_page = _postback(session, page_id, parent, page, match[0].xls_target).text
    chapters = [r for r in _child_rows(child_page) if r.xls_target and re.search(chapter, r.title)]
    if len(chapters) != 1:
        raise LookupError(f"CSB page {page_id} year {year}: {len(chapters)} chapters match {chapter!r}")
    r = _postback(session, page_id, parent, child_page, chapters[0].xls_target)
    if "text/html" in r.headers.get("Content-Type", ""):
        raise RuntimeError(f"CSB page {page_id} year {year}: got HTML instead of a file")
    cd = r.headers.get("Content-Disposition", "")
    name = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd)
    return r.content, (requests.utils.unquote(name.group(1)) if name else ""), chapters[0].title
