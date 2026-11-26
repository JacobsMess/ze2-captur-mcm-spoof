| Scenario | CPU model | Frames/s in | Lost (CAN ctrl / TWAI / TX / log) | IMA fwd latency avg / max | SPI busy | Core 0 / Core 1 load | GVRET stream |
|---|---|---|---|---|---|---|---|
| typical (EV 30%, IMA 40%, dash 30%) | 250 MIPS (IPC ~1.0) | 3,999 | 0 / 0 / 0 / 0 | 92 / 1259 us | 18 % | 18 % / 22 % | 112 kB/s |
| busy (EV 60%, IMA 70%, dash 60%) | 250 MIPS (IPC ~1.0) | 7,596 | 0 / 0 / 0 / 0 | 100 / 1750 us | 34 % | 28 % / 41 % | 208 kB/s |
| worst case (all four buses 100%) | 250 MIPS (IPC ~1.0) | 11,994 | 0 / 0 / 0 / 0 | 119 / 2372 us | 49 % | 38 % / 63 % | 321 kB/s |
| typical (EV 30%, IMA 40%, dash 30%) | 125 MIPS (IPC ~0.5) | 4,000 | 0 / 0 / 0 / 0 | 161 / 895 us | 28 % | 28 % / 44 % | 112 kB/s |
| busy (EV 60%, IMA 70%, dash 60%) | 125 MIPS (IPC ~0.5) | 7,609 | 0 / 0 / 0 / 0 | 177 / 2371 us | 50 % | 37 % / 70 % | 208 kB/s |
| worst case (all four buses 100%) | 125 MIPS (IPC ~0.5) | 12,018 | 0 / 0 / 0 / 0 | 275 / 2720 us | 73 % | 42 % / 92 % | 321 kB/s |
