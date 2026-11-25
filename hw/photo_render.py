"""Photo-style PCB render composited from KiCad 7 per-layer plots (top and bottom)."""
import subprocess
import sys

import cairosvg
import numpy as np
from PIL import Image
from scipy.ndimage import binary_fill_holes

PCB, OUT = sys.argv[1], sys.argv[2]
W = 2400


def layer(name, drill=0):
    svg = f"/tmp/_l_{name}.svg"
    subprocess.run(["kicad-cli", "pcb", "export", "svg", "--layers", f"{name},Edge.Cuts", "--black-and-white",
                    "--page-size-mode", "2", "--exclude-drawing-sheet", "--drill-shape-opt", str(drill), "-o", svg, PCB],
                   check=True, capture_output=True)
    png = svg[:-4] + ".png"
    cairosvg.svg2png(url=svg, write_to=png, output_width=W, background_color="white")
    return np.array(Image.open(png).convert("L")) < 128


def render(side):
    cu = layer(f"{side}.Cu", drill=2)
    cu_nodrill = layer(f"{side}.Cu", drill=0)
    mask_open = layer(f"{side}.Mask")
    silk = layer(f"{side}.SilkS")
    edge = layer("Edge.Cuts")
    holes = cu_nodrill & ~cu  # drill shapes knocked out of pads
    board = binary_fill_holes(edge)
    # slot: interior edge contour filled separately then removed
    from scipy.ndimage import label
    lab, n = label(~edge)
    outside = lab == lab[0, 0]
    board = ~outside
    inner = np.zeros_like(board)
    for i in range(1, n + 1):
        if i != lab[0, 0]:
            region = lab == i
            ys, xs = np.nonzero(region)
            if region.sum() < 0.02 * board.sum() and (xs.max() - xs.min()) < 0.05 * W:
                inner |= region  # the isolation slot
    board &= ~inner & ~edge | (edge & ~inner)
    img = np.zeros(cu.shape + (3,), np.float32)
    img[:] = (32, 36, 42)
    img[board] = (20, 92, 48)                            # solder mask over bare laminate
    img[board & cu] = (46, 132, 62)                      # copper under mask
    exposed = board & cu & mask_open
    img[exposed] = (205, 205, 200) if side == "F" else (200, 200, 196)  # HASL pads
    img[board & silk & ~mask_open] = (245, 245, 240)     # silkscreen
    img[holes | inner] = (32, 36, 42)
    img[edge & board] = (15, 60, 30)
    im = Image.fromarray(img.astype(np.uint8))
    if side == "B":
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    return im


for side, tag in (("F", "top"), ("B", "bottom")):
    render(side).save(f"{OUT}_{tag}.png")
    print("wrote", f"{OUT}_{tag}.png")
