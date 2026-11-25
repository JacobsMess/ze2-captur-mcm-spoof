| Scenario | CPU model | Frames/s in | Lost (CAN ctrl / TWAI / TX / log) | IMA fwd latency avg / max | SPI busy | Core 0 / Core 1 load | GVRET stream |
|---|---|---|---|---|---|---|---|
| typical (EV 30%, IMA 40%, dash 30%) | 250 MIPS (IPC ~1.0) | 3,998 | 0 / 0 / 0 / 0 | 92 / 670 us | 18 % | 18 % / 22 % | 112 kB/s |
| busy (EV 60%, IMA 70%, dash 60%) | 250 MIPS (IPC ~1.0) | 7,598 | 0 / 0 / 0 / 0 | 96 / 1112 us | 33 % | 29 % / 42 % | 208 kB/s |
| worst case (all four buses 100%) | 250 MIPS (IPC ~1.0) | 11,994 | 0 / 0 / 0 / 0 | 115 / 2285 us | 51 % | 36 % / 62 % | 320 kB/s |
| typical (EV 30%, IMA 40%, dash 30%) | 125 MIPS (IPC ~0.5) | 4,000 | 0 / 0 / 0 / 0 | 177 / 756 us | 30 % | 27 % / 46 % | 112 kB/s |
| busy (EV 60%, IMA 70%, dash 60%) | 125 MIPS (IPC ~0.5) | 7,598 | 0 / 0 / 0 / 0 | 167 / 1834 us | 48 % | 39 % / 68 % | 208 kB/s |
| worst case (all four buses 100%) | 125 MIPS (IPC ~0.5) | 12,009 | 0 / 0 / 0 / 0 | 255 / 2267 us | 69 % | 45 % / 90 % | 320 kB/s |
