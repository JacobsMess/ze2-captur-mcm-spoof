"""The JLCPCB files in hw/out/jlc against the board."""
import csv
import zipfile

import pcbnew
from conftest import HW, OX, OY, mm

JLC = HW / "out" / "jlc"


def rows(name):
    with open(JLC / name, newline="") as fh:
        return list(csv.DictReader(fh))


def bom_refs():
    refs = set()
    for r in rows("bom.csv"):
        refs |= {d.strip() for d in r["Designator"].split(",")}
    return refs


def test_cpl_matches_board(board):
    """Every BOM part is placed (SMT and THT connectors), each at its board position; THT rows at the body centre."""
    cpl = {r["Designator"]: r for r in rows("cpl.csv")}
    assert set(cpl) == bom_refs()
    offs = set()
    for ref, r in cpl.items():
        f = board.FindFootprintByReference(ref)
        p = f.GetPosition()
        if f.GetAttributes() & pcbnew.FP_THROUGH_HOLE:
            p = f.GetCourtyard(pcbnew.F_CrtYd).BBox().Centre()
        x, y = mm(p.x) - OX, -(mm(p.y) - OY)
        # kicad-cli writes positions relative to the page origin; compare offsets between parts instead
        offs.add((round(float(r["Mid X"].rstrip("mm")) - x, 2), round(float(r["Mid Y"].rstrip("mm")) - y, 2)))
    assert len(offs) == 1, f"CPL positions don't track the board: {sorted(offs)[:3]}"
    assert {"J1", "J2", "J3", "J4", "J6"} <= set(cpl), "THT connectors go to JLC with the SMT parts"


def test_bom_covers_every_placed_part():
    assert {r["Designator"] for r in rows("cpl.csv")} <= bom_refs()


def test_gerber_zip_complete():
    names = zipfile.ZipFile(JLC / "gerbers.zip").namelist()
    for ext in ("F_Cu", "In1_Cu", "In2_Cu", "B_Cu", "F_Mask", "B_Mask", "F_Silkscreen", "Edge_Cuts"):
        assert any(ext in n for n in names), ext
    assert any(n.endswith(".drl") for n in names)


def test_every_bom_line_has_an_lcsc_number_or_is_flagged():
    for r in rows("bom.csv"):
        assert r["LCSC Part #"] or r["Class"] == "G", r["Designator"]


def test_passives_use_basic_or_preferred_parts():
    # only the matched 0.1 % tap ladder, the 2512 HV series resistors (330R ladder ends, 10k sense ends) and parts
    # with no basic equivalent at JLC (crystal, PTCs, power inductor, the HV fuses) may add extended-part fees
    allowed = {"C406729", "C19866", "C270956", "C9010", "C960026", "C19078763", "C128694", "C178911"}
    for r in rows("bom.csv"):
        if r["Footprint"].startswith(("R_", "C_")) or r["LCSC Part #"] in allowed:
            assert r["Class"] in ("B", "P") or r["LCSC Part #"] in allowed, (r["Designator"], r["LCSC Part #"])
