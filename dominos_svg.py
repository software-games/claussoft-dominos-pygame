#!/usr/bin/env -S uv run --script

# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "svgwrite",
# ]
# ///

"""
Create SVG files for all 28 dominoes and save them in the `dominoes_svg` directory.

The SVG files are named `domino_i_j.svg` where `i` and `j` are the two numbers on the
domino.  Images are 200x400 pixels with the pips (dots) being 5.5% of the domino width.

% python3 -m venv .venv
% source .venv/bin/activate
% pip install --upgrade pip
% pip install svgwrite  # https://pypi.org/project/svgwrite
% python3 ./dominoes_svg.py
% open dominoes_svg/*
"""

# python3 ./dominoes_svg.py && open dominoes_svg/*
# from pyscript import display
# import pyodide
# display(dir(pyodide))
# asyncio.run(pyodide.load_package("micropip"))
# micropip = pyodide.pyimport("micropip")
# import micropip
# asyncio.run(micropip.install("svgwrite"))

# import pyodide_js
# asyncio.run(pyodide_js.loadPackage('svgwrite'))

import svgwrite
from svgwrite.drawing import Drawing

pip_offsets = (0.25, 0.5, 0.75)
pip_locations = (
    (()),
    ((1, 1),),
    ((0, 0), (2, 2)),
    ((0, 0), (1, 1), (2, 2)),
    ((0, 0), (0, 2), (2, 0), (2, 2)),
    ((0, 0), (0, 2), (1, 1), (2, 0), (2, 2)),
    ((0, 0), (0, 1), (0, 2), (2, 0), (2, 1), (2, 2)),
)


def svg_die(svg: Drawing, die: int, pip_count: int, width_in_px: int = 200) -> None:
    """
    Draw a single die (half of a domino) on the SVG canvas.
    die 0 is the top of the half of the domino. die 1 for the bottom half of the domino.
    pip_count is the number of pips (dots) on the die from 0 to 6.
    """
    assert die in (0, 1)
    assert 0 <= pip_count <= 6
    insert = (2, 2 + width_in_px * die)
    size = (width_in_px, width_in_px)
    svg.add(svg.rect(insert=insert, size=size, fill="white", stroke="blue"))
    # Now draw each of the pips...
    for x, y in pip_locations[pip_count]:
        center = (
            2 + pip_offsets[x] * width_in_px,
            2 + width_in_px * die + pip_offsets[y] * width_in_px,
        )
        # pip radius is 5.5% of the width so 11 pixels on a 200px wide domino
        svg.add(svg.circle(center=center, r=width_in_px * 0.055, fill="blue"))


def svg_domino(svg: Drawing, domino: tuple[int, int], width_in_px: int = 200) -> None:
    """
    Draw a domino on the SVG canvas by calling svg_die() for each half of the domino.
    """
    for die, pip_count in enumerate(domino):
        svg_die(svg, die, pip_count, width_in_px)


def dominoes_svg(width_in_px=200):
    """
    Create SVG files for all 28 dominoes and save them in the `dominoes_svg` directory.
    """
    x = 4
    y = 4
    for i in range(7):
        for j in range(i, 7):
            filename = f"dominoes_svg/domino_{i}_{j}.txt"
            size = (f"{width_in_px + x}px", f"{width_in_px * 2 + y}px")
            svg = svgwrite.Drawing(filename=filename, size=size)
            svg_domino(svg, (i, j), width_in_px)
            svg.save()


if __name__ == "__main__":
    dominoes_svg(width_in_px=200)
