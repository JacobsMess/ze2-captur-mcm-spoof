# One-board cost estimate (JLC assembly)

LCSC unit prices from `hw/jlc_parts.py`; loading fees per JLC's published schedule (Economic: per
Extended type; Standard: per Basic or Extended type). Setup, stencil, PCB fabrication and shipping are
not included: compare complete quotes for both services. JLC fits the ESP32-S3-WROOM-1 with Standard
assembly only; fit it by hand to keep the order on Economic assembly.

| Item | USD |
|---|---|
| Parts, one board (all lines) | 48.01 |
| Loading fees, Economic: 23 Extended SMT types x $3.07 | 71 |
| Loading fees, Standard: 52 Basic + Extended SMT types x $1.53 | 80 |
| THT connectors, 5 types (fit by hand) | - |

BOM lines by class: B 31, E 28, G 2, P 8 (B basic, P preferred, E extended, G not at JLC)

Not stocked at JLC: AQV214EHAX (~$6), TPS3431SDRBRQ1 (~$2). JLC global sourcing can buy them, or fit by hand.
