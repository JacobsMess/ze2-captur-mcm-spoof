# One-board cost estimate (JLC assembly)

LCSC unit prices from `hw/jlc_parts.py`; loading fees per JLC's published schedule (Economic: per
Extended type; Standard: per Basic or Extended type). Setup, stencil, PCB fabrication and shipping are
not included: compare complete quotes for both services. JLC fits the ESP32-S3-WROOM-1 with Standard
assembly only; fit it by hand to keep the order on Economic assembly.

| Item | USD |
|---|---|
| Parts, one board (all lines) | 52.65 |
| Loading fees, Economic: 27 Extended SMT types x $3.07 | 83 |
| Loading fees, Standard: 54 Basic + Extended SMT types x $1.53 | 83 |
| THT connectors, 5 types (JLC THT assembly: in bom.csv and cpl.csv, quote it) | - |

BOM lines by class: B 29, E 32, G 1, P 8 (B basic, P preferred, E extended, G not at JLC)

Not stocked at JLC: AQV214EHAX (~$6). JLC global sourcing can buy them, or fit by hand.
