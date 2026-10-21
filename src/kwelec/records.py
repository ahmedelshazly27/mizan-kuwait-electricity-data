"""The observation record every extractor emits, one per printed cell."""

from dataclasses import asdict, dataclass, fields

@dataclass
class Obs:
    source_id: str
    table_no: str
    variable: str
    level: str                      # national | plant | unit | sector
    period_start: str               # ISO date
    period_end: str
    frequency: str                  # annual | monthly | daily | instant
    value: str | None               # decimal as text, null when not a number as printed
    value_printed: str
    value_status: str               # number | dash | blank | text
    unit_printed: str
    row_label: str
    col_label: str
    method: str                     # xlsx | pdf_text | ocr | manual
    plant_id: str | None = None
    sector_id: str | None = None
    fuel: str | None = None
    technology: str | None = None
    unit_group: str | None = None
    observed_at: str | None = None
    page_pdf: int | None = None
    page_printed: str | None = None
    sheet: str | None = None
    cell_ref: str | None = None
    cell_formula: str | None = None
    ocr_confidence: float | None = None
    footnote_printed: str | None = None

    def row(self) -> dict:
        return asdict(self)

FIELDS = [f.name for f in fields(Obs)]
