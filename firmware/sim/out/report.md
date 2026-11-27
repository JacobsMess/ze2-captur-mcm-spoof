| Scenario | CPU model | Frames/s in | Lost (CAN ctrl / TWAI / TX / log) | IMA fwd latency avg / max | SPI busy | Core 0 / Core 1 load | GVRET stream |
|---|---|---|---|---|---|---|---|
| typical (EV 30%, IMA 40%, dash 30%) | 250 MIPS (IPC ~1.0) | 3,999 | 0 / 0 / 0 / 0 | 94 / 782 us | 18 % | 18 % / 23 % | 114 kB/s |
| busy (EV 60%, IMA 70%, dash 60%) | 250 MIPS (IPC ~1.0) | 7,600 | 0 / 0 / 0 / 0 | 94 / 1453 us | 33 % | 30 % / 42 % | 210 kB/s |
| worst case (all four buses 100%) | 250 MIPS (IPC ~1.0) | 11,991 | 0 / 0 / 0 / 0 | 99 / 1420 us | 50 % | 38 % / 64 % | 322 kB/s |
| typical (EV 30%, IMA 40%, dash 30%) | 125 MIPS (IPC ~0.5) | 4,001 | 0 / 0 / 0 / 0 | 165 / 1942 us | 28 % | 28 % / 42 % | 115 kB/s |
| busy (EV 60%, IMA 70%, dash 60%) | 125 MIPS (IPC ~0.5) | 7,603 | 0 / 0 / 0 / 0 | 177 / 1938 us | 50 % | 37 % / 70 % | 210 kB/s |
| worst case (all four buses 100%) | 125 MIPS (IPC ~0.5) | 11,998 | 0 / 0 / 0 / 0 | 248 / 3546 us | 72 % | 43 % / 91 % | 322 kB/s |
