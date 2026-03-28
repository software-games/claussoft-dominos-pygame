#!/usr/bin/env -S uv run --script

# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "lxml",
# ]
# ///

"""
Pretty-print SVG files in the `dominoes_svg/` directory using lxml.

Usage:
    python3 svg_format.py          # formats all *.svg files under dominoes_svg/
    python3 svg_format.py a.svg    # formats the given file(s)
"""

import sys
from pathlib import Path

from lxml import etree


def format_svg(path: Path) -> bool:
    """Parse and pretty-print a single SVG file in place.

    Returns True on success, False on error.
    """
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return False
    try:
        tree = etree.parse(str(path))
    except etree.XMLSyntaxError as exc:
        print(f"Skipping {path}: {exc}", file=sys.stderr)
        return False
    tree.write(
        str(path),
        encoding="utf-8",
        xml_declaration=True,
        pretty_print=True,
    )
    print(f"Formatted {path}")
    return True


def main() -> None:
    paths: list[Path]
    if len(sys.argv) > 1:
        paths = [Path(p) for p in sys.argv[1:]]
    else:
        svg_dir = Path("dominoes_svg")
        if not svg_dir.is_dir():
            print(f"Directory not found: {svg_dir}", file=sys.stderr)
            sys.exit(1)
        paths = sorted(svg_dir.glob("*.svg"))
        if not paths:
            print(f"No SVG files found in {svg_dir}", file=sys.stderr)
            sys.exit(1)

    errors = sum(1 for path in paths if not format_svg(path))
    if errors:
        sys.exit(errors)


if __name__ == "__main__":
    main()
