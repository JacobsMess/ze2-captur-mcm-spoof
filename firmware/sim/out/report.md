| Scenario | CPU model | Frames/s in | Lost (CAN ctrl / TWAI / TX / log) | IMA fwd latency avg / max | SPI busy | Core 0 / Core 1 load | GVRET stream |
|---|---|---|---|---|---|---|---|
| typical (EV 30%, IMA 40%, dash 30%) | 250 MIPS (IPC ~1.0) | 3,999 | 0 / 0 / 0 / 0 | 92 / 817 us | 18 % | 18 % / 22 % | 114 kB/s |
| busy (EV 60%, IMA 70%, dash 60%) | 250 MIPS (IPC ~1.0) | 7,607 | 0 / 0 / 0 / 0 | 93 / 1301 us | 33 % | 28 % / 41 % | 210 kB/s |
| worst case (all four buses 100%) | 250 MIPS (IPC ~1.0) | 11,990 | 0 / 0 / 0 / 0 | 99 / 811 us | 51 % | 36 % / 62 % | 322 kB/s |
| typical (EV 30%, IMA 40%, dash 30%) | 125 MIPS (IPC ~0.5) | 3,999 | 0 / 0 / 0 / 0 | 162 / 981 us | 28 % | 27 % / 44 % | 114 kB/s |
| busy (EV 60%, IMA 70%, dash 60%) | 125 MIPS (IPC ~0.5) | 7,604 | 0 / 0 / 0 / 0 | 167 / 1091 us | 50 % | 38 % / 71 % | 211 kB/s |
| worst case (all four buses 100%) | 125 MIPS (IPC ~0.5) | 12,001 | 0 / 0 / 0 / 0 | 266 / 1601 us | 73 % | 42 % / 93 % | 322 kB/s |
