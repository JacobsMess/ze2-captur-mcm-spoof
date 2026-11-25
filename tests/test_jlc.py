"""The JLCPCB files in hw/out/jlc against the board."""
import csv
import zipfile

import pcbnew
from conftest import HW, OX, OY, mm

JLC = HW / "out" / "jlc"


def rows(name):
    with open(JLC / name, newline="") as fh:
        return list(csv.DictReader(fh))


def smd_refs(board):
    return {f.GetReference() for f in board.GetFootprints()
            if f.GetAttributes() & pcbnew.FP_SMD and not f.GetAttributes() & pcbnew.FP_EXCLUDE_FROM_POS_FILES}


def test_cpl_matches_board(board):
    cpl = {r["Designator"]: r for r in rows("cpl.csv")}
    assert set(cpl) == smd_refs(board)
    for ref, r in cpl.items():
        f = board.FindFootprintByReference(ref)
        x, y = mm(f.GetPosition().x) - OX, -(mm(f.GetPosition().y) - OY)
        # kicad-cli writes positions relative to the page origin; compare offsets between parts instead
        r["_xy"] = (float(r["Mid X"].rstrip("mm")) - x, float(r["Mid Y"].rstrip("mm")) - y)
    offs = {tuple(round(v, 2) for v in r["_xy"]) for r in cpl.values()}
    assert len(offs) == 1, f"CPL positions don't track the board: {sorted(offs)[:3]}"


def test_bom_covers_every_placed_part():
    bom = set()
    for r in rows("bom.csv"):
        bom |= {d.strip() for d in r["Designator"].split(",")}
    assert {r["Designator"] for r in rows("cpl.csv")} <= bom


def test_gerber_zip_complete():
    names = zipfile.ZipFile(JLC / "gerbers.zip").namelist()
    for ext in ("F_Cu", "In1_Cu", "In2_Cu", "B_Cu", "F_Mask", "B_Mask", "F_Silkscreen", "Edge_Cuts"):
        assert any(ext in n for n in names), ext
    assert any(n.endswith(".drl") for n in names)


def test_every_bom_line_has_an_lcsc_number_or_is_flagged():
    for r in rows("bom.csv"):
        assert r["LCSC Part #"] or r["Class"] == "G", r["Designator"]


def test_passives_use_basic_or_preferred_parts():
    # only the matched 0.1 % tap ladder, the 2512 HV series resistors and parts with no basic
    # equivalent at JLC (crystal, PTCs, power inductor) may add extended-part fees
    allowed = {"C2828891", "C54315", "C9010", "C960026", "C19078763", "C128694"}
    for r in rows("bom.csv"):
        if r["Footprint"].startswith(("R_", "C_")) or r["LCSC Part #"] in allowed:
            assert r["Class"] in ("B", "P") or r["LCSC Part #"] in allowed, (r["Designator"], r["LCSC Part #"])
