| Scenario | CPU model | Frames/s in | Lost (CAN ctrl / TWAI / TX / log) | IMA fwd latency avg / max | SPI busy | Core 0 / Core 1 load | GVRET stream |
|---|---|---|---|---|---|---|---|
| typical (EV 30%, IMA 40%, dash 30%) | 250 MIPS (IPC ~1.0) | 3,998 | 0 / 0 / 0 / 0 | 94 / 798 us | 18 % | 18 % / 23 % | 114 kB/s |
| busy (EV 60%, IMA 70%, dash 60%) | 250 MIPS (IPC ~1.0) | 7,603 | 0 / 0 / 0 / 0 | 91 / 846 us | 33 % | 29 % / 41 % | 210 kB/s |
| worst case (all four buses 100%) | 250 MIPS (IPC ~1.0) | 11,992 | 0 / 0 / 0 / 0 | 99 / 869 us | 51 % | 37 % / 62 % | 322 kB/s |
| typical (EV 30%, IMA 40%, dash 30%) | 125 MIPS (IPC ~0.5) | 3,999 | 0 / 0 / 0 / 0 | 158 / 1504 us | 27 % | 28 % / 43 % | 114 kB/s |
| busy (EV 60%, IMA 70%, dash 60%) | 125 MIPS (IPC ~0.5) | 7,606 | 0 / 0 / 0 / 0 | 171 / 1130 us | 50 % | 38 % / 70 % | 211 kB/s |
| worst case (all four buses 100%) | 125 MIPS (IPC ~0.5) | 12,010 | 0 / 0 / 0 / 0 | 266 / 1989 us | 73 % | 42 % / 92 % | 323 kB/s |
