"""Firmware safety chain on the host: captur/safety/contactors/ignition/control/zombie compiled with gcc against
the board model in tests/host/control_test.c, one scenario per process."""
import shutil
import subprocess

import pytest

from conftest import ROOT

MAIN = ROOT / "firmware" / "main"
HOST = ROOT / "tests" / "host"
SRCS = ["captur.c", "safety.c", "contactors.c", "ignition.c", "control.c", "zombie.c"]


@pytest.fixture(scope="module")
def binary(tmp_path_factory):
    if not shutil.which("gcc"):
        pytest.skip("gcc not installed")
    exe = tmp_path_factory.mktemp("host") / "control_test"
    cmd = ["gcc", "-std=gnu11", "-Wall", "-Werror", "-O1", "-DCONFIG_ZE2_SIM=1",   # sim build's CAN ID layouts
           f"-I{HOST / 'stub'}", f"-I{MAIN}", "-o", str(exe), str(HOST / "control_test.c")]
    cmd += [str(MAIN / s) for s in SRCS]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return exe


SCENARIOS = ["normal_close", "only_cells", "stale_groups_stage2", "live_link_while_open", "soft_trip_before_start",
             "soft_trip_while_closed", "pack_disagrees_with_cells", "welded_neg", "welded_pos", "sense_invalid",
             "sense_lost_while_closed", "stall_and_resume", "crank_dip_keeps_trip", "decoder_checks"]


def test_scenario_list_is_complete(binary):
    listed = subprocess.run([str(binary)], capture_output=True, text=True, check=True).stdout.split()
    assert listed == SCENARIOS


@pytest.mark.parametrize("name", SCENARIOS)
def test_control_scenario(binary, name):
    r = subprocess.run([str(binary), name], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
