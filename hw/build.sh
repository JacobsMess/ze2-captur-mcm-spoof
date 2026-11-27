#!/usr/bin/env bash
# Whole board build, from the scripts to the JLC files and the README images. Run with KiCad 7's Python.
#   KRT_DIR=<KiCadRoutingTools checkout, router built> ./build.sh          ECO: re-route only what changed (minutes)
#   KRT_DIR=... ./build.sh full                                             route everything from scratch (~30 min)
#   RENDER=1 ...                                                            also the ray-traced renders (needs bpy, 3D libs)
set -euo pipefail
cd "$(dirname "$0")"
: "${KRT_DIR:?set KRT_DIR to a KiCadRoutingTools checkout with the router built}"
export KRT_DIR
B=build
mkdir -p "$B"

python3 project.py ze2-mcm-spoof
python3 build_board.py "$B/unrouted.kicad_pcb"
for e in pro dru; do cp "ze2-mcm-spoof.kicad_$e" "$B/unrouted.kicad_$e"; done

if [ "${1:-}" = full ]; then
  python3 krt_route.py "$B/unrouted.kicad_pcb" "$B/routed.kicad_pcb"
else
  python3 krt_route.py "$B/unrouted.kicad_pcb" "$B/routed.kicad_pcb" ze2-mcm-spoof.kicad_pcb
fi
while [ -n "$(python3 cleanup.py "$B/routed.kicad_pcb")" ]; do :; done
python3 widen_power.py "$B/routed.kicad_pcb" "$B/finished.kicad_pcb"
python3 tidy_silk.py "$B/finished.kicad_pcb" "$B/tidy.kicad_pcb"
for e in pro dru; do cp "ze2-mcm-spoof.kicad_$e" "$B/tidy.kicad_$e"; done
python3 fab.py "$B/tidy.kicad_pcb" ze2-mcm-spoof.kicad_pcb out/jlc
mv out/jlc/drc_report.txt out/drc_report.txt
grep "^\*\* Found" out/drc_report.txt

python3 photo_render.py ze2-mcm-spoof.kicad_pcb ../docs/img/layers
python3 ../docs/schematic.py
if [ -n "${RENDER:-}" ]; then
  EXPORT_DIR=scene xvfb-run -a python3 render3d.py ze2-mcm-spoof.kicad_pcb ../docs/img/layers_top.png x
  python3 blender_render.py scene/scene.json ../docs/img/board 64 1800
fi
(cd .. && python3 -m pytest -q)
