# One-board cost estimate (JLC assembly)

LCSC unit prices from `hw/jlc_parts.py`; fees are JLC's standard-assembly figures. PCB fabrication and
shipping are not included. JLC fits the ESP32-S3-WROOM-1 with Standard assembly only; fit it by hand to
keep the order on Economic assembly.

| Item | USD |
|---|---|
| Parts, one board (all lines) | 48.00 |
| Extended-part fees, 22 SMT types x $3 | 66 |
| Extended-part fees, 5 THT connectors (skip: fit them by hand) | 15 |

BOM lines by class: B 31, E 27, G 2, P 8 (B basic, P preferred, E extended, G not at JLC)

Not stocked at JLC: AQV214EHAX (~$6), TPS3431SDRBRQ1 (~$2). JLC global sourcing can buy them, or fit by hand.
