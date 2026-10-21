from decimal import Decimal

from kwelec.extract.mew_text import row_cells
from kwelec.extract.xlsx_fmt import displayed
from kwelec.normalize import parse_printed


def test_numbers_and_non_numbers():
    assert parse_printed("1,234.5") == (Decimal("1234.5"), "number")
    assert parse_printed("‏-279‎") == (Decimal("-279"), "number")
    assert parse_printed("٣٤٥") == (Decimal("345"), "number")
    assert parse_printed("-") == (None, "dash")
    assert parse_printed("_") == (None, "dash")      # MEW 2020 prints "_" where later editions print "-"
    assert parse_printed("") == (None, "blank")
    assert parse_printed("804+25") == (None, "text")  # never added up
    assert parse_printed("30/7/2020") == (None, "text")


def test_spreadsheet_display():
    assert displayed(95249645.07, "#,##0") == "95,249,645"
    assert displayed(5491657.0600000005, "General") == "5491657.06"
    assert displayed(1540, "0.0") == "1540.0"
    assert displayed(12418426.602, "#,##0.000") == "12,418,426.602"


def test_mew_cells():
    _, cs = row_cells("Grand Total  املجموع الكلى358065   3463936 3271370")
    assert [c["printed"] for c in cs] == ["358065", "3463936", "3271370"]
    _, cs = row_cells("7414   -   600.0   2511   )720 +(25   -   1998")
    assert [c["printed"] for c in cs] == ["7414", "-", "600.0", "2511", ")720 +(25", "-", "1998"]
    _, cs = row_cells("56.9   74.0   * 66356   8401   * 74757   2020")
    assert [(c["printed"], c["marker"]) for c in cs][2] == ("66356", "*")
    _, cs = row_cells("6   50   01&02/08/2012   5.6   11850   2012")
    assert cs[2]["printed"] == "01&02/08/2012"
