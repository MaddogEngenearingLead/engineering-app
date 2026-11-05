from app.services.embedded_bom import _columns, _qty, _type_of


def test_qty_forms():
    assert _qty("9") == (9, "ea", "")
    assert _qty("+/- 160'") == (160, "ft", "Approximate length")
    assert _qty("AS REQ.")[0] == 1


def test_type_and_columns():
    assert _type_of('2", THREDOLET FOR 8" THRU 10" PIPE') == "fitting"
    assert _type_of('120 DEGREE FRP PAD, 12" LONG FOR 8" PIPE') == "support"
    assert _type_of('10", PIPE, 0.365" W.T.') == "piping"
    cols = _columns(["ITEM #", "PRODUCT DESCRIPTION", "MANUFACTURER", "PART NO.", "QTY.", "SUPPLIED", "INSTALLED"])
    assert cols["qty"] == 4 and cols["desc"] == 1
