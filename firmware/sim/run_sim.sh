#!/usr/bin/env bash
# Build the simulation firmware and run it on Espressif's ESP32-S3 QEMU with instruction counting.
#   shift=2: 4 ns per instruction (250 MIPS, ~1 instruction per clock at 240 MHz: optimistic)
#   shift=3: 8 ns per instruction (125 MIPS, ~0.5 per clock: pessimistic, allows for cache/flash stalls)
# Needs ESP-IDF v5.4 exported (idf.py, qemu-system-xtensa on PATH).
set -euo pipefail
cd "$(dirname "$0")/.."
idf.py -B build_sim -D SDKCONFIG=build_sim/sdkconfig -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.sim" \
    set-target esp32s3 build
(cd build_sim && python -m esptool --chip esp32s3 merge_bin --fill-flash-size 8MB -o flash_sim.bin @flash_args)
mkdir -p sim/out
for s in 2 3; do
  # QEMU keeps running after the firmware prints SIMDONE: stop it once the results are in
  (timeout 3000 qemu-system-xtensa -nographic -machine esp32s3 \
    -drive file=build_sim/flash_sim.bin,if=mtd,format=raw,readonly=on -icount shift=$s,align=off \
    | tee sim/out/qemu_shift$s.log | sed -u '/SIMDONE/q' > /dev/null
   pkill -f "qemu-system-xtensa.*shift=$s," || true) &
done
wait
python3 sim/report.py sim/out/qemu_shift2.log sim/out/qemu_shift3.log > sim/out/report.md
cat sim/out/report.md
