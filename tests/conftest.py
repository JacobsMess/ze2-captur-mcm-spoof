"""Shared fixtures. Run with a Python that can `import pcbnew` (KiCad 7's, or the system one on Linux)."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HW = ROOT / "hw"
PCB = HW / "ze2-mcm-spoof.kicad_pcb"
sys.path.insert(0, str(HW))

pcbnew = pytest.importorskip("pcbnew")
OX = OY = 50.0  # build_board.py places the board origin at (50, 50) mm


def mm(v):
    return pcbnew.ToMM(v)


@pytest.fixture(scope="session")
def board():
    return pcbnew.LoadBoard(str(PCB))


@pytest.fixture(scope="session")
def parts():
    return json.loads((HW / "parts.json").read_text())


@pytest.fixture(scope="session")
def drc(board, tmp_path_factory):
    """KiCad DRC (zones refilled first). Returns {violation type: [block text, ...]}."""
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    out = tmp_path_factory.mktemp("drc") / "drc.txt"
    pcbnew.WriteDRCReport(board, str(out), pcbnew.EDA_UNITS_MILLIMETRES, True)
    text = out.read_text()
    found = {}
    for blk in re.split(r"\n(?=\[)", text):
        m = re.match(r"\[(\w+)\]", blk)
        if m:
            found.setdefault(m.group(1), []).append(blk.strip())
    found["_unconnected_count"] = int(re.search(r"Found (\d+) unconnected", text).group(1))
    return found


def counts(drc):
    return Counter({k: len(v) for k, v in drc.items() if not k.startswith("_")})
