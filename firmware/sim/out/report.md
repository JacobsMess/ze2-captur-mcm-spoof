| Scenario | CPU model | Frames/s in | Lost (MCP2515 / TWAI / TX / log) | IMA fwd latency avg / max | SPI busy | Core 0 / Core 1 load | GVRET stream |
|---|---|---|---|---|---|---|---|
| typical (EV 30%, IMA 40%, dash 30%) | 250 MIPS (IPC ~1.0) | 3,999 | 24 / 0 / 0 / 0 | 71 / 654 us | 15 % | 18 % / 20 % | 112 kB/s |
| busy (EV 60%, IMA 70%, dash 60%) | 250 MIPS (IPC ~1.0) | 7,607 | 130 / 0 / 0 / 0 | 72 / 760 us | 28 % | 26 % / 36 % | 208 kB/s |
| worst case (all four buses 100%) | 250 MIPS (IPC ~1.0) | 12,005 | 475 / 0 / 0 / 0 | 70 / 721 us | 42 % | 35 % / 54 % | 318 kB/s |
| typical (EV 30%, IMA 40%, dash 30%) | 125 MIPS (IPC ~0.5) | 4,004 | 16 / 0 / 0 / 0 | 110 / 728 us | 19 % | 28 % / 27 % | 112 kB/s |
| busy (EV 60%, IMA 70%, dash 60%) | 125 MIPS (IPC ~0.5) | 7,609 | 168 / 0 / 0 / 0 | 118 / 1003 us | 34 % | 40 % / 50 % | 207 kB/s |
| worst case (all four buses 100%) | 125 MIPS (IPC ~0.5) | 12,015 | 1309 / 0 / 0 / 0 | 130 / 987 us | 52 % | 45 % / 70 % | 315 kB/s |
