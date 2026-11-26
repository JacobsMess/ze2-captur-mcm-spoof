"""Turn the SIMRESULT lines from the QEMU runs into a markdown table.

usage: python3 report.py qemu_shift2.log qemu_shift3.log > report.md
"""
import json
import re
import sys

SPEED = {"2": "250 MIPS (IPC ~1.0)", "3": "125 MIPS (IPC ~0.5)"}
SCENARIOS = 3
CT_CLOSED = 5     # contactors.h: the sim BMS is healthy, so the sequencer must finish closed


def load(path):
    out, done = [], False
    for line in open(path, errors="ignore"):
        if line.startswith("SIMRESULT "):
            out.append(json.loads(line[len("SIMRESULT "):]))
        done |= line.startswith("SIMDONE")
    if not done or len(out) != SCENARIOS:
        sys.exit(f"{path}: incomplete run ({len(out)} of {SCENARIOS} results, SIMDONE {'seen' if done else 'missing'})")
    bad = [r["scenario"] for r in out if r["contactors"] != CT_CLOSED]
    if bad:
        sys.exit(f"{path}: contactors not closed in {bad}")
    return out


def main(paths):
    print("| Scenario | CPU model | Frames/s in | Lost (CAN ctrl / TWAI / TX / log) | IMA fwd latency avg / max | "
          "SPI busy | Core 0 / Core 1 load | GVRET stream |")
    print("|---|---|---|---|---|---|---|---|")
    for p in paths:
        shift = re.search(r"shift(\d)", p).group(1)
        for r in load(p):
            s = r["seconds"]
            fin = sum(r["generated"].values()) / s
            lost = (r["mcp_rx_overflows"], r["twai_queue_overflows"], r["tx_drops"], r["log_drops"])
            lat = r["fwd_latency_us"]
            cpu = r["cpu_pct"]
            print(f"| {r['scenario']} | {SPEED[shift]} | {fin:,.0f} | {' / '.join(map(str, lost))} | "
                  f"{lat['avg']} / {lat['max']} us | {r['spi_busy_pct']:.0f} % | "
                  f"{cpu['core0_minus_sim']:.0f} % / {cpu['core1']:.0f} % | {r['gvret_kbyte_s']:.0f} kB/s |")


if __name__ == "__main__":
    main(sys.argv[1:])
