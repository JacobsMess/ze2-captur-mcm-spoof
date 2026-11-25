| Scenario | CPU model | Frames/s in | Lost (CAN ctrl / TWAI / TX / log) | IMA fwd latency avg / max | SPI busy | Core 0 / Core 1 load | GVRET stream |
|---|---|---|---|---|---|---|---|
| typical (EV 30%, IMA 40%, dash 30%) | 250 MIPS (IPC ~1.0) | 3,998 | 0 / 0 / 0 / 0 | 92 / 665 us | 18 % | 18 % / 22 % | 112 kB/s |
| busy (EV 60%, IMA 70%, dash 60%) | 250 MIPS (IPC ~1.0) | 7,603 | 0 / 0 / 0 / 0 | 94 / 1597 us | 32 % | 29 % / 40 % | 208 kB/s |
| worst case (all four buses 100%) | 250 MIPS (IPC ~1.0) | 11,991 | 0 / 0 / 0 / 0 | 100 / 1624 us | 49 % | 38 % / 65 % | 320 kB/s |
| typical (EV 30%, IMA 40%, dash 30%) | 125 MIPS (IPC ~0.5) | 3,998 | 0 / 0 / 0 / 0 | 162 / 1034 us | 28 % | 28 % / 42 % | 112 kB/s |
| busy (EV 60%, IMA 70%, dash 60%) | 125 MIPS (IPC ~0.5) | 7,605 | 0 / 0 / 0 / 0 | 184 / 2590 us | 51 % | 37 % / 71 % | 208 kB/s |
| worst case (all four buses 100%) | 125 MIPS (IPC ~0.5) | 12,015 | 0 / 0 / 0 / 0 | 262 / 1941 us | 73 % | 42 % / 92 % | 320 kB/s |
