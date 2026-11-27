"""Firmware on the host: the safety chain (captur/safety/contactors/ignition/control/zombie) and the peripherals
(pump, NTC lines) compiled with gcc against the board models in tests/host/, one scenario per process."""
import shutil
import subprocess

import pytest

from conftest import ROOT

MAIN = ROOT / "firmware" / "main"
HOST = ROOT / "tests" / "host"
BINARIES = {
    "control_test": ["captur.c", "safety.c", "contactors.c", "ignition.c", "control.c", "zombie.c"],
    "peripheral_test": ["pump.c", "spoof.c"],
}
SCENARIOS = {
    "control_test": ["normal_close", "only_cells", "stale_groups_stage2", "live_link_while_open",
                     "soft_trip_before_start", "soft_trip_while_closed", "pack_disagrees_with_cells", "welded_pos",
                     "welded_pre", "sense_invalid", "sense_lost_while_closed", "stall_and_resume",
                     "crank_dip_keeps_trip", "decoder_checks", "keepalive_frames", "main_stuck_open",
                     "main_stuck_open_full_link",
                     "soft_trip_during_precharge", "link_reads_high", "late_precharge", "ignition_sense_lost",
                     "reset_latch", "taps_need_island", "clock_wrap",
                     "precharge_coil_open", "precharge_coil_shorted", "precharge_stuck_on"],
    "peripheral_test": ["ntc_measures_mcm_input", "ntc_trim_absorbs_dac_error", "ntc_no_pullup_falls_back",
                        "pump_onoff_default", "pump_open_circuit", "pump_q3_failed", "pump_signal_mode",
                        "pump_pwm_mode", "island_loss_reported"],
}


@pytest.fixture(scope="module")
def binaries(tmp_path_factory):
    if not shutil.which("gcc"):
        pytest.skip("gcc not installed")
    out = {}
    d = tmp_path_factory.mktemp("host")
    for name, srcs in BINARIES.items():
        exe = d / name
        cmd = ["gcc", "-std=gnu11", "-Wall", "-Werror", "-O1", f"-I{HOST / 'stub'}", f"-I{MAIN}", "-o", str(exe),
               str(HOST / f"{name}.c")] + [str(MAIN / s) for s in srcs] + ["-lm"]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        out[name] = exe
    return out


@pytest.mark.parametrize("name", BINARIES)
def test_scenario_list_is_complete(binaries, name):
    listed = subprocess.run([str(binaries[name])], capture_output=True, text=True, check=True).stdout.split()
    assert listed == SCENARIOS[name]


@pytest.mark.parametrize("name,scenario", [(n, s) for n, ss in SCENARIOS.items() for s in ss])
def test_scenario(binaries, name, scenario):
    r = subprocess.run([str(binaries[name]), scenario], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
