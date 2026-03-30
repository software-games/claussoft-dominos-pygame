#!/usr/bin/env -S uv run --script

"""
Running this script opens a PyScript-based graphical user interface for
playing racehorse dominos in the local web browser.

The game board looks similar to images/tkDomino.py.png but uses PyScript
instead of tkinter.  Dominos are SVG images consistent with dominos_svg.py.
Each player is dealt 7 random dominos shown in boxes at the top and bottom.
The remaining dominos are placed face-down in the boneyard on the left.
The first player can drag a domino from their hand into the play area.
"""

# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "beautifulsoup4",
#     "httpx",
#     "pydantic",
# ]
# ///

import random
import sys
import tempfile
import webbrowser
from pathlib import Path

import httpx
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel

PYSCRIPT_VERSION = "2026.3.1"
PYSCRIPT_JS_URL = f"https://pyscript.net/releases/{PYSCRIPT_VERSION}/core.js"
PYSCRIPT_CSS_URL = f"https://pyscript.net/releases/{PYSCRIPT_VERSION}/core.css"

# Pip locations consistent with dominos_svg.py (0-6 pips)
PIP_OFFSETS = (0.25, 0.5, 0.75)
PIP_LOCATIONS: tuple[tuple[tuple[int, int], ...], ...] = (
    (),
    ((1, 1),),
    ((0, 0), (2, 2)),
    ((0, 0), (1, 1), (2, 2)),
    ((0, 0), (0, 2), (2, 0), (2, 2)),
    ((0, 0), (0, 2), (1, 1), (2, 0), (2, 2)),
    ((0, 0), (0, 1), (0, 2), (2, 0), (2, 1), (2, 2)),
)


class GameState(BaseModel):
    """Pydantic model capturing a complete racehorse dominos game state."""

    player0_hand: list[list[int]]  # human player (shown at bottom)
    player1_hand: list[list[int]]  # computer player (shown at top)
    boneyard: list[list[int]]  # bones not yet dealt, shown face-down
    play_chain: list[list[int]] = []
    scores: list[int] = [0, 0]
    current_player: int = 0
    game_num: int = 0  # incremented at the start of each new hand; first_player = game_num % 2
    message: str = "Your turn: drag a domino from your hand to the play area."


def all_domino_bones() -> list[list[int]]:
    """Return all 28 unique domino bones as [low, high] pairs."""
    return [[i, j] for i in range(7) for j in range(i, 7)]


def deal_game() -> GameState:
    """Shuffle all 28 bones and deal 7 each; the rest go to the boneyard."""
    bones = all_domino_bones()
    random.shuffle(bones)
    return GameState(
        player0_hand=bones[:7],
        player1_hand=bones[7:14],
        boneyard=bones[14:],
    )


def _half_svg(pip: int, half: int, pad: int, w: int) -> str:
    """Return SVG elements for one half of a domino (one die face)."""
    y0 = pad + half * w
    parts: list[str] = [
        f'<rect x="{pad}" y="{y0}" width="{w}" height="{w}" fill="white" stroke="blue" stroke-width="1"/>'
    ]
    r = max(2.0, w * 0.055)
    for xi, yi in PIP_LOCATIONS[pip]:
        cx = pad + PIP_OFFSETS[xi] * w
        cy = y0 + PIP_OFFSETS[yi] * w
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="blue"/>')
    return "".join(parts)


def make_domino_svg(top: int, bottom: int, *, w: int = 55, face_down: bool = False) -> str:
    """Generate an inline SVG string for one domino bone.

    Args:
        top: pip count for the top half (0-6).
        bottom: pip count for the bottom half (0-6).
        w: width of each half in pixels; the full bone is w x (2*w).
        face_down: when True the bone is rendered as a plain grey rectangle.
    """
    h, pad = w * 2, 3
    tw, th = w + 2 * pad, h + 2 * pad
    rx = w // 10

    if face_down:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw}" height="{th}">'
            f'<rect x="{pad}" y="{pad}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="#666" stroke="#444" stroke-width="1.5"/>'
            f"</svg>"
        )

    dy = pad + w
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw}" height="{th}">'
        f"{_half_svg(top, 0, pad, w)}"
        f"{_half_svg(bottom, 1, pad, w)}"
        f'<line x1="{pad}" y1="{dy}" x2="{pad + w}" y2="{dy}" '
        f'stroke="blue" stroke-width="1.5"/>'
        f"</svg>"
    )


# ---------------------------------------------------------------------------
# Python code that runs inside the browser via PyScript
# ---------------------------------------------------------------------------
_PYSCRIPT_CODE = """\
import json
import random

from pyscript import document, ffi, window

# ---------------------------------------------------------------------------
# Game constants
# ---------------------------------------------------------------------------
_SPINNER_MULTIPLIER = 2   # doubles score both open ends of a spinner
_SCORING_DIVISOR = 5      # racehorse: score a point for every 5 pips
_WIN_SCORE = 30           # first player to reach this score wins the match
_BONEYARD_MIN = 2         # must leave at least this many bones in boneyard
_BONE_GAP_PX = 4          # uniform gap (px) between adjacent dominos in every direction

# ---------------------------------------------------------------------------
# Pip data (mirrors the host-side PIP_OFFSETS / PIP_LOCATIONS)
# ---------------------------------------------------------------------------
_PIP_OFFSETS = (0.25, 0.5, 0.75)
_PIP_LOCATIONS = (
    (),
    ((1, 1),),
    ((0, 0), (2, 2)),
    ((0, 0), (1, 1), (2, 2)),
    ((0, 0), (0, 2), (2, 0), (2, 2)),
    ((0, 0), (0, 2), (1, 1), (2, 0), (2, 2)),
    ((0, 0), (0, 1), (0, 2), (2, 0), (2, 1), (2, 2)),
)


def _half_svg(pip, half, pad, w):
    y0 = pad + half * w
    r = max(2.0, w * 0.055)
    parts = [
        f'<rect x="{pad}" y="{y0}" width="{w}" height="{w}" '
        f'fill="white" stroke="blue" stroke-width="1"/>'
    ]
    for xi, yi in _PIP_LOCATIONS[pip]:
        cx = pad + _PIP_OFFSETS[xi] * w
        cy = y0 + _PIP_OFFSETS[yi] * w
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="blue"/>'
        )
    return "".join(parts)


def _half_svg_h(pip, half, pad, w):
    x0 = pad + half * w
    r = max(2.0, w * 0.055)
    parts = [
        f'<rect x="{x0}" y="{pad}" width="{w}" height="{w}" '
        f'fill="white" stroke="blue" stroke-width="1"/>'
    ]
    for xi, yi in _PIP_LOCATIONS[pip]:
        cx = x0 + _PIP_OFFSETS[xi] * w
        cy = pad + _PIP_OFFSETS[yi] * w
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="blue"/>'
        )
    return "".join(parts)


def _domino_svg_h(top, bottom, w=55, face_down=False):
    h, pad = w * 2, 3
    tw, th = h + 2 * pad, w + 2 * pad
    rx = w // 10
    if face_down:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw}" height="{th}">'
            f'<rect x="{pad}" y="{pad}" width="{h}" height="{w}" rx="{rx}" '
            f'fill="#666" stroke="#444" stroke-width="1.5"/></svg>'
        )
    dx = pad + w
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw}" height="{th}">'
        f"{_half_svg_h(top, 0, pad, w)}"
        f"{_half_svg_h(bottom, 1, pad, w)}"
        f'<line x1="{dx}" y1="{pad}" x2="{dx}" y2="{pad + w}" '
        f'stroke="blue" stroke-width="1.5"/></svg>'
    )


def _domino_svg(top, bottom, w=55, face_down=False):
    h, pad = w * 2, 3
    tw, th = w + 2 * pad, h + 2 * pad
    rx = w // 10
    if face_down:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw}" height="{th}">'
            f'<rect x="{pad}" y="{pad}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="#666" stroke="#444" stroke-width="1.5"/></svg>'
        )
    dy = pad + w
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw}" height="{th}">'
        f"{_half_svg(top, 0, pad, w)}"
        f"{_half_svg(bottom, 1, pad, w)}"
        f'<line x1="{pad}" y1="{dy}" x2="{pad + w}" y2="{dy}" '
        f'stroke="blue" stroke-width="1.5"/></svg>'
    )


# ---------------------------------------------------------------------------
# Game state (mutable; starts from the JSON embedded by the host script)
# ---------------------------------------------------------------------------
_raw = json.loads(document.getElementById("game-state-data").textContent)
_hand0 = [list(t) for t in _raw["player0_hand"]]   # human hand
_hand1 = [list(t) for t in _raw["player1_hand"]]   # computer hand
_boneyard = [list(t) for t in _raw["boneyard"]]
_chain: list[list[int]] = []   # played dominos, in chain order
_left_end: int | None = None   # open left end of the chain
_right_end: int | None = None  # open right end of the chain
_scores = [0, 0]
_current_player = 0            # 0 = human, 1 = computer
_needs_boneyard_draw = False   # True when human must draw from boneyard
_game_over = False             # True when the match has been won
_consecutive_passes = 0        # tracks back-to-back passes; game stuck when >= 2
_game_num = _raw.get("game_num", 0)  # how many hands dealt so far (first player alternates)
_spinner_val = None            # pip value of first double placed (the spinner)
_top_branch = []               # bones in the top branch above the spinner
_bottom_branch = []            # bones in the bottom branch below the spinner
_top_end = None                # open pip at the end of the top branch
_bottom_end = None             # open pip at the end of the bottom branch


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------
def _make_bone_div(top, bottom, draggable=False, face_down=False,
                   horizontal=False, from_boneyard=False, w=55):
    div = document.createElement("div")
    div.className = "domino-bone"
    div.setAttribute("data-top", str(top))
    div.setAttribute("data-bottom", str(bottom))
    if from_boneyard:
        div.setAttribute("data-from-boneyard", "true")
    div.setAttribute("draggable", "true" if draggable else "false")
    if horizontal:
        div.innerHTML = _domino_svg_h(top, bottom, w=w, face_down=face_down)
    else:
        div.innerHTML = _domino_svg(top, bottom, w=w, face_down=face_down)
    return div


def _render_hand(hand, area_id, draggable=False, face_down=False, horizontal=False):
    area = document.getElementById(area_id)
    area.innerHTML = ""
    for bone in hand:
        bone_div = _make_bone_div(bone[0], bone[1], draggable=draggable,
                                  face_down=face_down, horizontal=horizontal)
        area.appendChild(bone_div)
    if draggable:
        for el in area.querySelectorAll(".domino-bone[draggable='true']"):
            el.addEventListener("dragstart", ffi.create_proxy(_on_dragstart))


def _render_boneyard(draggable_to_hand=False):
    area = document.getElementById("boneyard-area")
    area.innerHTML = ""
    lbl = document.createElement("div")
    lbl.className = "area-label"
    lbl.textContent = f"Boneyard ({len(_boneyard)})"
    area.appendChild(lbl)
    for bone in _boneyard:
        bone_div = _make_bone_div(
            bone[0], bone[1],
            draggable=draggable_to_hand,
            face_down=True,  # always face-down; player must not see values
            horizontal=True,
            from_boneyard=True,
        )
        area.appendChild(bone_div)
    if draggable_to_hand:
        for el in area.querySelectorAll(".domino-bone[draggable='true']"):
            el.addEventListener("dragstart", ffi.create_proxy(_on_dragstart_boneyard))
    area.className = "draw-mode" if draggable_to_hand else ""


def _apply_bone_rotation(div, w):
    # CSS-rotate the whole landscape bone 90° to appear portrait (perpendicular to chain).
    # Margin compensation makes the element occupy portrait-sized space in the flex layout:
    #   natural box: (2w+6) wide x (w+6) tall
    #   after rotate: appears (w+6) wide x (2w+6) tall
    #   delta = w -> shrink horizontal by w/2 each side, grow vertical by w/2 each side
    div.className += " bone-rotated"
    hw = w // 2
    div.style.marginTop = f"{hw}px"
    div.style.marginBottom = f"{hw}px"
    div.style.marginLeft = f"-{hw}px"
    div.style.marginRight = f"-{hw}px"


def _render_linear_chain(area, w):
    for i, bone in enumerate(_chain):
        is_double = bone[0] == bone[1]
        # All bones use the landscape (horizontal) SVG.
        # Doubles are CSS-rotated 90° so they appear portrait, perpendicular to the chain.
        div = _make_bone_div(bone[0], bone[1], horizontal=True, w=w)
        if is_double:
            _apply_bone_rotation(div, w)
        if i == 0 or i == len(_chain) - 1:
            end_side = "left" if i == 0 else "right"
            div.setAttribute("data-chain-end", end_side)
            div.addEventListener("dragover", ffi.create_proxy(_on_dragover))
            div.addEventListener("drop", ffi.create_proxy(_on_drop_chain_bone))
        area.appendChild(div)


def _render_cross_chain(area, w, si):
    # Bones to the left of the spinner
    for i in range(si):
        bone = _chain[i]
        is_double = bone[0] == bone[1]
        div = _make_bone_div(bone[0], bone[1], horizontal=True, w=w)
        if is_double:
            _apply_bone_rotation(div, w)
        if i == 0:
            div.setAttribute("data-chain-end", "left")
            div.addEventListener("dragover", ffi.create_proxy(_on_dragover))
            div.addEventListener("drop", ffi.create_proxy(_on_drop_chain_bone))
        area.appendChild(div)

    # Spinner junction: column of [top branch / spinner / bottom branch]
    junc = document.createElement("div")
    junc.className = "spinner-junction"

    # Bone pixel height: SVG vertical height (2*w + 6px padding) plus flex gap.
    bone_h = 2 * w + 6 + _BONE_GAP_PX
    max_branch_h = max(len(_top_branch), len(_bottom_branch)) * bone_h

    top_col = document.createElement("div")
    top_col.className = "branch-col"
    # Give both columns equal min-height so the spinner stays vertically centred.
    top_col.style.minHeight = f"{max_branch_h}px"
    # Push bones downward (toward the spinner).
    top_col.style.justifyContent = "flex-end"
    if _top_branch:
        # Render outermost bone first (reversed order → tip at top of column).
        # Bones are stored as [connector, free_end]; swap so free end faces outward (up).
        # Doubles are landscape (perpendicular to vertical branch direction).
        for b in reversed(_top_branch):
            is_dbl = b[0] == b[1]
            bd = _make_bone_div(b[1], b[0], horizontal=is_dbl, w=w)
            top_col.appendChild(bd)
        fc = top_col.firstChild
        fc.setAttribute("data-chain-end", "top")
        fc.addEventListener("dragover", ffi.create_proxy(_on_dragover))
        fc.addEventListener("drop", ffi.create_proxy(_on_drop_chain_bone))
    junc.appendChild(top_col)

    # Spinner bone: drop on top half → top branch, bottom half → bottom branch.
    # No visual highlight — just a transparent drop target on the bone itself.
    sp_bone = _chain[si]
    sp_div = _make_bone_div(sp_bone[0], sp_bone[1], w=w)
    sp_div.setAttribute("data-chain-end", "spinner")
    sp_div.addEventListener("dragover", ffi.create_proxy(_on_dragover))
    sp_div.addEventListener("drop", ffi.create_proxy(_on_drop_spinner_bone))
    junc.appendChild(sp_div)

    bot_col = document.createElement("div")
    bot_col.className = "branch-col"
    bot_col.style.minHeight = f"{max_branch_h}px"
    if _bottom_branch:
        # Render closest-to-spinner bone first (forward order → connector at top, touching spinner).
        # Doubles are landscape (perpendicular to vertical branch direction).
        for b in _bottom_branch:
            is_dbl = b[0] == b[1]
            bd = _make_bone_div(b[0], b[1], horizontal=is_dbl, w=w)
            bot_col.appendChild(bd)
        lc = bot_col.lastChild
        lc.setAttribute("data-chain-end", "bottom")
        lc.addEventListener("dragover", ffi.create_proxy(_on_dragover))
        lc.addEventListener("drop", ffi.create_proxy(_on_drop_chain_bone))
    junc.appendChild(bot_col)

    area.appendChild(junc)

    # Bones to the right of the spinner
    for i in range(si + 1, len(_chain)):
        bone = _chain[i]
        is_double = bone[0] == bone[1]
        div = _make_bone_div(bone[0], bone[1], horizontal=True, w=w)
        if is_double:
            _apply_bone_rotation(div, w)
        if i == len(_chain) - 1:
            div.setAttribute("data-chain-end", "right")
            div.addEventListener("dragover", ffi.create_proxy(_on_dragover))
            div.addEventListener("drop", ffi.create_proxy(_on_drop_chain_bone))
        area.appendChild(div)


def _render_play_area():
    area = document.getElementById("play-area")
    area.innerHTML = ""
    if not _chain:
        return
    w = _compute_bone_size()
    si = _spinner_index()
    if si is not None and _spinner_is_surrounded():
        _render_cross_chain(area, w, si)
    else:
        _render_linear_chain(area, w)


def _render_scores():
    document.getElementById("score-p0").textContent = str(_scores[0])
    document.getElementById("score-p1").textContent = str(_scores[1])


def _set_message(msg):
    area = document.getElementById("status-msg")
    p = document.createElement("p")
    p.textContent = msg
    area.appendChild(p)
    area.scrollTop = area.scrollHeight


def _render_all():
    is_human_turn = _current_player == 0 and not _game_over
    _render_hand(_hand0, "player0-hand",
                 draggable=is_human_turn and not _needs_boneyard_draw)
    _render_hand(_hand1, "player1-hand", face_down=True)
    _render_boneyard(draggable_to_hand=_needs_boneyard_draw)
    _render_play_area()
    _render_scores()
    play_area = document.getElementById("play-area")
    if _needs_boneyard_draw or not is_human_turn:
        play_area.style.pointerEvents = "none"
        play_area.style.opacity = "0.5"
    else:
        play_area.style.pointerEvents = "auto"
        play_area.style.opacity = "1"


# ---------------------------------------------------------------------------
# Game logic helpers
# ---------------------------------------------------------------------------
def _is_double(bone):
    return bone[0] == bone[1]


def _hand_value(hand):
    return sum(t[0] + t[1] for t in hand)


def _score_chain():
    if not _chain:
        return 0
    if len(_chain) == 1 and _chain[0][0] == _chain[0][1]:
        total = _chain[0][0] * _SPINNER_MULTIPLIER
    else:
        lv, rv, tv, bv = _end_values()
        total = lv + rv + tv + bv
    return total if total % _SCORING_DIVISOR == 0 else 0


def _simulate_chain_score_after_play(bone):
    # Return the best possible chain score after playing this bone on any valid end.
    a, b = bone[0], bone[1]
    if not _chain:
        total = a * 2 if a == b else a + b
        return total if total % _SCORING_DIVISOR == 0 else 0
    lv, rv, tv, bv = _end_values()
    mult = 2 if a == b else 1
    best = 0
    for tgt in _play_options(a, b):
        new_end = (b if a == _ref_pip(tgt) else a) * mult
        total = _total_for_target(tgt, new_end, lv, rv, tv, bv)
        sc = total if total % _SCORING_DIVISOR == 0 else 0
        best = max(best, sc)
    return best


def _find_bone(hand, top, bottom):
    for bone in hand:
        if bone == [top, bottom] or bone == [bottom, top]:
            return bone
    return None


def _end_values():
    # Return (lv, rv, tv, bv): current chain end pip values with doubles counted twice.
    lv = (_left_end or 0) * (2 if _chain[0][0] == _chain[0][1] else 1)
    rv = (_right_end or 0) * (2 if _chain[-1][0] == _chain[-1][1] else 1)
    top_dbl = _top_branch and _top_branch[-1][0] == _top_branch[-1][1]
    tv = ((_top_end or 0) * (2 if top_dbl else 1)) if _top_branch else 0
    bot_dbl = _bottom_branch and _bottom_branch[-1][0] == _bottom_branch[-1][1]
    bv = ((_bottom_end or 0) * (2 if bot_dbl else 1)) if _bottom_branch else 0
    return lv, rv, tv, bv


def _ref_pip(tgt):
    # Return the reference pip value for a given target end.
    if tgt == "left":
        return _left_end
    if tgt == "right":
        return _right_end
    if tgt == "top":
        return _top_end if _top_end is not None else _spinner_val
    return _bottom_end if _bottom_end is not None else _spinner_val


def _total_for_target(tgt, new_end, lv, rv, tv, bv):
    # Return the chain end sum after placing new_end at tgt (other ends unchanged).
    if tgt == "left":
        return new_end + rv + tv + bv
    if tgt == "right":
        return lv + new_end + tv + bv
    if tgt == "top":
        return lv + rv + new_end + bv
    return lv + rv + tv + new_end


def _extend_branch(branch, end_ref, top, bottom):
    # Extend a spinner branch by one bone. end_ref is a 1-element list [current_end].
    # Mutates branch and end_ref[0] in-place; returns True on success.
    ref = end_ref[0] if end_ref[0] is not None else _spinner_val
    if top == ref:
        branch.append([top, bottom])
        end_ref[0] = bottom
    elif bottom == ref:
        branch.append([bottom, top])
        end_ref[0] = top
    else:
        return False
    return True


def _apply_play(top, bottom, hand, target_end=None):
    global _left_end, _right_end, _spinner_val, _top_end, _bottom_end
    bone = _find_bone(hand, top, bottom)
    if bone is None:
        return False
    # First bone: always valid, no target needed
    if not _chain:
        hand.remove(bone)
        _chain.append([top, bottom])
        _left_end = top
        _right_end = bottom
        if top == bottom and _spinner_val is None:
            _spinner_val = top
        return True
    # Auto-detect target when not specified
    if target_end is None:
        opts = _play_options(top, bottom)
        if not opts:
            return False
        if len(opts) > 1:
            return False  # ambiguous; caller must specify
        target_end = opts[0]
    hand.remove(bone)
    if target_end == "left":
        if top == _left_end:
            _chain.insert(0, [bottom, top])
            _left_end = bottom
        elif bottom == _left_end:
            _chain.insert(0, [top, bottom])
            _left_end = top
        else:
            hand.append(bone)
            return False
    elif target_end == "right":
        if top == _right_end:
            _chain.append([top, bottom])
            _right_end = bottom
        elif bottom == _right_end:
            _chain.append([bottom, top])
            _right_end = top
        else:
            hand.append(bone)
            return False
    elif target_end in ("top", "bottom"):
        if _spinner_val is None or not _spinner_is_surrounded():
            hand.append(bone)
            return False
        branch = _top_branch if target_end == "top" else _bottom_branch
        end_ref = [_top_end] if target_end == "top" else [_bottom_end]
        if not _extend_branch(branch, end_ref, top, bottom):
            hand.append(bone)
            return False
        if target_end == "top":
            _top_end = end_ref[0]
        else:
            _bottom_end = end_ref[0]
    else:
        hand.append(bone)
        return False
    # Record first double as spinner
    if _spinner_val is None and top == bottom:
        _spinner_val = top
    return True


def _can_play(top, bottom):
    if not _chain:
        return True
    return len(_play_options(top, bottom)) > 0


def _valid_plays(hand):
    return [t for t in hand if _can_play(t[0], t[1])]


def _spinner_index():
    # Find the spinner (the first double), identified by both halves equaling spinner_val.
    if _spinner_val is None:
        return None
    for i, b in enumerate(_chain):
        if b[0] == _spinner_val and b[1] == _spinner_val:
            return i
    return None


def _spinner_is_surrounded():
    si = _spinner_index()
    if si is None:
        return False
    return 0 < si < len(_chain) - 1


def _play_options(top, bottom):
    # Returns list of valid target ends for an existing chain.
    opts = []
    can_left = _left_end is not None and (top == _left_end or bottom == _left_end)
    can_right = _right_end is not None and (top == _right_end or bottom == _right_end)
    if can_left and can_right and _left_end == _right_end:
        opts.append("right")  # both ends same value - pick right (append) as canonical
    else:
        if can_left:
            opts.append("left")
        if can_right:
            opts.append("right")
    if _spinner_val is not None and _spinner_is_surrounded():
        sv = _spinner_val
        if _top_end is None:
            if top == sv or bottom == sv:
                opts.append("top")
        elif top == _top_end or bottom == _top_end:
            opts.append("top")
        if _bottom_end is None:
            if top == sv or bottom == sv:
                opts.append("bottom")
        elif top == _bottom_end or bottom == _bottom_end:
            opts.append("bottom")
    return opts


def _is_ambiguous_play(top, bottom):
    # Return True when the bone fits more than one placement position.
    return len(_play_options(top, bottom)) > 1


def _compute_bone_size():
    # Return the largest domino half-width (w) that fits all chain bones.
    if not _chain:
        return 55
    area = document.getElementById("play-area")
    avail = int(area.clientWidth) - 20  # subtract padding
    if avail <= 50:
        avail = 650  # fallback when DOM not yet laid out
    h_bones = sum(1 for b in _chain if b[0] != b[1])
    v_bones = len(_chain) - h_bones
    n = len(_chain)
    gaps = max(0, n - 1) * _BONE_GAP_PX
    # At half-width w: horizontal bone = (2w+6) px wide, vertical = (w+6) px wide.
    # Solve: h_bones*(2w+6) + v_bones*(w+6) + gaps <= avail
    coeff = 2 * h_bones + v_bones
    if coeff <= 0:
        return 55
    w = (avail - 6 * n - gaps) / coeff

    # Height constraint for cross-chain: reduce w so spinner branches fit vertically.
    si = _spinner_index()
    if si is not None and _spinner_is_surrounded():
        max_b = max(len(_top_branch), len(_bottom_branch))
        if max_b > 0:
            # Viewport height minus UI overhead (h1 + two hand rows + status + gaps).
            win_h = int(document.documentElement.clientHeight)
            avail_h = win_h - 280  # ~280px overhead
            if avail_h > 60:
                # bone_h = 2w + 6 + g (g = _BONE_GAP_PX)
                # junction_h = 2*max_b*bone_h + (2w+6)
                #            = w*(4*max_b+2) + (12+2g)*max_b + 6
                # Solve for w: w <= (avail_h - (12+2g)*max_b - 6) / (4*max_b + 2)
                gap = _BONE_GAP_PX
                num = avail_h - (12 + 2 * gap) * max_b - 6
                denom = 4 * max_b + 2
                if denom > 0 and num > 0:
                    w = min(w, num / denom)

    return max(10, min(55, int(w)))


# ---------------------------------------------------------------------------
# Win / end-of-hand logic
# ---------------------------------------------------------------------------
def _show_new_game_button():
    btn = document.getElementById("new-game-btn")
    if btn:
        btn.style.display = "inline-block"


def _check_win_after_play(player_idx):
    # Player emptied their hand: award bonus pts and check for match win.
    global _game_over
    opp_hand = _hand1 if player_idx == 0 else _hand0
    bonus = _hand_value(opp_hand) // _SCORING_DIVISOR
    _scores[player_idx] += bonus
    _render_scores()
    winner_name = "You" if player_idx == 0 else "Computer"
    if _scores[player_idx] >= _WIN_SCORE:
        _game_over = True
        _render_all()
        _set_message(
            f"{winner_name} wins the match with {_scores[player_idx]} points! "
            f"(+{bonus} pts from opponent's hand)"
        )
        _show_new_game_button()
    else:
        _render_all()
        _set_message(
            f"{winner_name} cleared the hand! +{bonus} bonus pts. "
            f"Scores: You {_scores[0]}, CPU {_scores[1]}. Dealing new hand..."
        )
        _deal_new_hand()


def _deal_new_hand():
    # Shuffle and deal a fresh set of bones, preserving match scores.
    global _hand0, _hand1, _boneyard, _chain, _left_end, _right_end
    global _current_player, _needs_boneyard_draw, _consecutive_passes, _game_num
    global _spinner_val, _top_end, _bottom_end
    bones = [[i, j] for i in range(7) for j in range(i, 7)]
    random.shuffle(bones)
    _hand0 = [list(t) for t in bones[:7]]
    _hand1 = [list(t) for t in bones[7:14]]
    _boneyard = [list(t) for t in bones[14:]]
    _chain.clear()
    _left_end = None
    _right_end = None
    _spinner_val = None
    _top_branch.clear()
    _bottom_branch.clear()
    _top_end = None
    _bottom_end = None
    _game_num += 1
    _needs_boneyard_draw = False
    _consecutive_passes = 0
    first_player = _game_num % 2
    first_name = "Computer" if first_player == 1 else "You"
    goes = "goes" if first_player == 1 else "go"
    _set_message(f"New hand dealt! {first_name} {goes} first.")
    _start_turn(first_player)


def _end_stuck_game():
    # Called when both players pass in a row - award points to the player with fewer pips.
    global _game_over
    v0 = _hand_value(_hand0)
    v1 = _hand_value(_hand1)
    if v0 < v1:
        winner_idx, bonus = 0, v1 // _SCORING_DIVISOR
    elif v1 < v0:
        winner_idx, bonus = 1, v0 // _SCORING_DIVISOR
    else:
        _game_over = True
        _render_all()
        _set_message("Game stuck - both hands equal. No winner this hand.")
        _show_new_game_button()
        return
    _scores[winner_idx] += bonus
    _render_scores()
    winner_name = "You" if winner_idx == 0 else "Computer"
    if _scores[winner_idx] >= _WIN_SCORE:
        _game_over = True
        _render_all()
        _set_message(f"Game stuck! {winner_name} wins the match with {_scores[winner_idx]} pts!")
        _show_new_game_button()
    else:
        _render_all()
        _set_message(
            f"Game stuck! {winner_name} had fewer pips, gains {bonus} pts. "
            f"Scores: You {_scores[0]}, CPU {_scores[1]}. Dealing new hand..."
        )
        _deal_new_hand()


# ---------------------------------------------------------------------------
# Turn management: start_turn handles boneyard draws and switches players
# ---------------------------------------------------------------------------
def _start_turn(player_idx, prefix=""):
    # Begin a turn for player_idx, drawing from boneyard if necessary.
    global _current_player, _needs_boneyard_draw, _consecutive_passes
    _current_player = player_idx
    _needs_boneyard_draw = False
    hand = _hand0 if player_idx == 0 else _hand1
    if _valid_plays(hand):
        _render_all()
        if player_idx == 1:
            _set_message(prefix + "Computer's turn...")
            _computer_play()
        else:
            _set_message(prefix + "Your turn: drag a domino to the play area.")
    elif len(_boneyard) > _BONEYARD_MIN:
        if player_idx == 1:
            _render_all()
            _set_message(prefix + "Computer draws from boneyard...")
            _computer_draw_and_play()
        else:
            _needs_boneyard_draw = True
            _render_all()
            _set_message(prefix + "No playable bones! Drag a bone from the Boneyard to your hand.")
    else:
        _consecutive_passes += 1
        if _consecutive_passes >= 2:
            _end_stuck_game()
        else:
            other = 1 - player_idx
            _render_all()
            _set_message(
                prefix +
                f"{'You' if player_idx == 0 else 'Computer'} passes "
                f"(no valid bones, boneyard too small). "
                f"{'Computer' if player_idx == 0 else 'Your'} turn."
            )
            _start_turn(other)


def _after_play(player_idx, bone_played):
    # Called after player successfully places a bone; handles scoring, go-again, and win.
    global _consecutive_passes
    _consecutive_passes = 0
    hand = _hand0 if player_idx == 0 else _hand1
    pts = _score_chain()
    scored = pts > 0
    is_dbl = _is_double(bone_played)
    if scored:
        _scores[player_idx] += pts // _SCORING_DIVISOR
    if not hand:
        # Player emptied their hand. Per racehorse rules: if the last bone was a double
        # or scored, the player must draw from the boneyard and keep playing.
        if (scored or is_dbl) and len(_boneyard) > _BONEYARD_MIN:
            player_name = "You" if player_idx == 0 else "Computer"
            if is_dbl and scored:
                prefix = (
                    f"{player_name} played a double and scored "
                    f"{pts // _SCORING_DIVISOR} pt(s) with their last bone! "
                    f"Must draw and keep playing. "
                )
            elif is_dbl:
                prefix = (
                    f"{player_name} played their last bone (a double)! "
                    f"Must draw and keep playing. "
                )
            else:
                prefix = (
                    f"{player_name} scored {pts // _SCORING_DIVISOR} pt(s) "
                    f"with their last bone! Must draw and keep playing. "
                )
            _start_turn(player_idx, prefix=prefix)
        else:
            _check_win_after_play(player_idx)
        return
    if scored or is_dbl:
        if is_dbl and scored:
            prefix = (
                f"{'You' if player_idx == 0 else 'Computer'} played a double "
                f"and scored {pts // _SCORING_DIVISOR} pt(s)! Go again. "
            )
        elif is_dbl:
            prefix = f"{'You' if player_idx == 0 else 'Computer'} played a double! Go again. "
        else:
            prefix = (
                f"{'You' if player_idx == 0 else 'Computer'} scored "
                f"{pts // _SCORING_DIVISOR} pt(s)! Go again. "
            )
        _start_turn(player_idx, prefix=prefix)
    else:
        _start_turn(1 - player_idx)


# ---------------------------------------------------------------------------
# Computer player
# ---------------------------------------------------------------------------
def _computer_draw_and_play():
    # Computer draws from boneyard until it can play (or boneyard gets too small).
    drawn_count = 0
    while not _valid_plays(_hand1) and len(_boneyard) > _BONEYARD_MIN:
        drawn = _boneyard.pop(random.randrange(len(_boneyard)))
        _hand1.append(drawn)
        drawn_count += 1
    _render_all()
    if drawn_count:
        draw_msg = f"Computer drew {drawn_count} bone(s) from the boneyard. "
    else:
        draw_msg = ""
    if _valid_plays(_hand1):
        _set_message(draw_msg + "Computer's turn...")
        _computer_play()
    else:
        global _consecutive_passes
        _consecutive_passes += 1
        if _consecutive_passes >= 2:
            _end_stuck_game()
        else:
            _set_message(draw_msg + "Computer passes - no valid bones. Your turn.")
            _start_turn(0)


def _computer_play():
    # Computer picks the best available bone and plays it.
    plays = _valid_plays(_hand1)
    if not plays:
        return
    # Rank plays: prefer (1) scoring plays by pts, (2) doubles for go-again,
    # (3) highest pip total to shed high-value bones from hand.
    best = max(
        plays,
        key=lambda t: (
            _simulate_chain_score_after_play(t),
            _is_double(t),
            t[0] + t[1],
        ),
    )
    # Pick the best target end for this bone (highest scoring; first option as tiebreak)
    opts = _play_options(best[0], best[1]) if _chain else []
    tgt = opts[0] if opts else None
    if len(opts) > 1:
        a, b = best[0], best[1]
        lv, rv, tv, bv = _end_values()
        mult = 2 if a == b else 1
        best_sc = -1
        for o in opts:
            ne = (b if a == _ref_pip(o) else a) * mult
            tot = _total_for_target(o, ne, lv, rv, tv, bv)
            sc = tot if tot % _SCORING_DIVISOR == 0 else 0
            if sc > best_sc:
                best_sc = sc
                tgt = o
    if _apply_play(best[0], best[1], _hand1, target_end=tgt):
        _set_message(f"Computer played [{best[0]}|{best[1]}].")
        _after_play(1, best)
    else:
        _set_message("Computer could not play - passing.")
        _start_turn(0)


# ---------------------------------------------------------------------------
# Drag-and-drop handlers
# ---------------------------------------------------------------------------
def _on_dragstart(event):
    top = event.target.getAttribute("data-top")
    bottom = event.target.getAttribute("data-bottom")
    event.dataTransfer.setData("text/plain", f"{top},{bottom}")
    event.dataTransfer.effectAllowed = "move"


def _on_dragstart_boneyard(event):
    # Boneyard bones are face-down; transfer only a draw signal (no pip values revealed).
    event.dataTransfer.setData("text/plain", "boneyard:draw")
    event.dataTransfer.effectAllowed = "move"


def _on_dragover(event):
    event.preventDefault()
    event.dataTransfer.dropEffect = "move"


def _on_drop(event):
    event.preventDefault()
    if _current_player != 0 or _needs_boneyard_draw or _game_over:
        return
    # If the drop landed on a chain-end or spinner bone, that element's dedicated
    # handler takes priority (guards against stopPropagation not firing through proxies).
    if event.target.closest("[data-chain-end]"):
        return
    data = event.dataTransfer.getData("text/plain")
    if data.startswith("boneyard:"):
        return  # boneyard bones go to hand, not play area
    top_s, bottom_s = data.split(",")
    top, bottom = int(top_s), int(bottom_s)
    if not _can_play(top, bottom):
        _set_message(f"[{top}|{bottom}] cannot be played here - try another bone.")
        return
    opts = _play_options(top, bottom)
    lr_opts = [o for o in opts if o in ("left", "right")]
    sp_opts = [o for o in opts if o in ("top", "bottom")]
    # Bone only fits the spinner branches - guide player to drop on the spinner bone.
    if sp_opts and not lr_opts:
        _set_message(
            f"[{top}|{bottom}] fits the spinner! Drop it on the central double bone "
            f"(top half for above, bottom half for below)."
        )
        return
    # Bone fits both a chain end and the spinner - require a targeted drop.
    if lr_opts and sp_opts:
        ends_str = " or ".join(f"the {o} end" for o in lr_opts)
        _set_message(
            f"[{top}|{bottom}] fits multiple positions! Drop it on {ends_str} "
            f"or on the central double bone for a branch."
        )
        return
    # Truly ambiguous between left and right chain ends.
    if len(lr_opts) > 1:
        _set_message(
            f"[{top}|{bottom}] fits both ends! Drop it on the leftmost or rightmost bone."
        )
        return
    if _apply_play(top, bottom, _hand0):
        _after_play(0, [top, bottom])
    else:
        _set_message("That move is not valid.")


def _on_drop_spinner_bone(event):
    # Hand bone dropped directly onto the spinner bone - use Y position to pick top/bottom.
    event.preventDefault()
    event.stopPropagation()
    if _current_player != 0 or _needs_boneyard_draw or _game_over:
        return
    data = event.dataTransfer.getData("text/plain")
    if data.startswith("boneyard:"):
        return
    top_s, bottom_s = data.split(",")
    top, bottom = int(top_s), int(bottom_s)
    # Determine top vs bottom from where on the bone the drop occurred.
    offset_y = event.offsetY
    el_h = event.currentTarget.offsetHeight
    target_end = "top" if offset_y < el_h / 2 else "bottom"
    if not _can_play(top, bottom):
        _set_message(f"[{top}|{bottom}] cannot be played here - try another bone.")
        return
    if _apply_play(top, bottom, _hand0, target_end=target_end):
        _after_play(0, [top, bottom])
    else:
        half = "top" if target_end == "top" else "bottom"
        _set_message(
            f"[{top}|{bottom}] does not fit the {half} branch. "
            f"Try dropping on the other half of the double."
        )


def _on_drop_chain_bone(event):
    # Hand bone dropped directly onto a chain-end bone - directed placement.
    event.preventDefault()
    event.stopPropagation()
    if _current_player != 0 or _needs_boneyard_draw or _game_over:
        return
    chain_end = event.currentTarget.getAttribute("data-chain-end")
    if not chain_end:
        return
    data = event.dataTransfer.getData("text/plain")
    if data.startswith("boneyard:"):
        return
    top_s, bottom_s = data.split(",")
    top, bottom = int(top_s), int(bottom_s)
    if not _can_play(top, bottom):
        _set_message(f"[{top}|{bottom}] cannot be played here - try another bone.")
        return
    if _apply_play(top, bottom, _hand0, target_end=chain_end):
        _after_play(0, [top, bottom])
    else:
        _set_message(f"[{top}|{bottom}] does not fit on the {chain_end} end.")


def _on_drop_boneyard_to_hand(event):
    # Boneyard bone dropped onto the human's hand area.
    global _needs_boneyard_draw, _consecutive_passes
    event.preventDefault()
    if not _needs_boneyard_draw or _game_over:
        return
    data = event.dataTransfer.getData("text/plain")
    if not data.startswith("boneyard:"):
        return
    if not _boneyard:
        return
    # Bones are face-down: always pick a random bone regardless of which was dragged.
    idx = random.randrange(len(_boneyard))
    bone = _boneyard.pop(idx)
    _hand0.append(bone)
    if _valid_plays(_hand0) or len(_boneyard) <= _BONEYARD_MIN:
        _needs_boneyard_draw = False
        if _valid_plays(_hand0):
            _render_all()
            _set_message("Drew a bone from the boneyard. Your turn: drag a domino to the play area.")
        else:
            _consecutive_passes += 1
            if _consecutive_passes >= 2:
                _end_stuck_game()
            else:
                _render_all()
                _set_message("Drew a bone but still no playable bones. Computer's turn.")
                _start_turn(1)
    else:
        _render_all()
        _set_message("Drew a bone from the boneyard. Still no playable bones - draw another.")


def _on_new_game(event):  # noqa: ARG001
    window.location.reload()


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
_play_area = document.getElementById("play-area")
_play_area.addEventListener("dragover", ffi.create_proxy(_on_dragover))
_play_area.addEventListener("drop", ffi.create_proxy(_on_drop))

_hand0_area = document.getElementById("player0-hand")
_hand0_area.addEventListener("dragover", ffi.create_proxy(_on_dragover))
_hand0_area.addEventListener("drop", ffi.create_proxy(_on_drop_boneyard_to_hand))

_new_game_btn = document.getElementById("new-game-btn")
if _new_game_btn:
    _new_game_btn.addEventListener("click", ffi.create_proxy(_on_new_game))

_render_all()
document.getElementById("status-msg").innerHTML = ""
_set_message(_raw["message"])
"""


# ---------------------------------------------------------------------------
# CSS for the game board
# ---------------------------------------------------------------------------
_CSS = """\
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: sans-serif;
    background: #2d5a1b;
    color: #fff;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 8px;
    gap: 6px;
    overflow-y: auto;
}
h1 { font-size: 1.1rem; letter-spacing: 2px; }
#board {
    display: grid;
    grid-template-columns: 130px 1fr 130px;
    grid-template-rows: auto auto auto;
    gap: 6px;
    width: 100%;
}
.player-hand {
    grid-column: 1 / -1;
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    background: rgba(0,0,0,.3);
    border-radius: 8px;
    padding: 6px;
    min-height: 70px;
    align-items: center;
    justify-content: space-evenly;
}
#boneyard-area {
    display: flex;
    flex-direction: column;
    gap: 3px;
    background: rgba(0,0,0,.4);
    border-radius: 8px;
    padding: 6px;
    align-items: center;
    align-self: start;
    overflow-y: auto;
}
#play-area {
    background: rgba(255,255,255,.08);
    border: 2px dashed rgba(255,255,255,.4);
    border-radius: 8px;
    display: flex;
    flex-direction: row;
    flex-wrap: nowrap;
    gap: 4px;
    padding: 8px;
    align-items: center;
    justify-content: center;
    height: fit-content;
    align-self: center;
}
#scoreboard {
    display: flex;
    flex-direction: column;
    gap: 8px;
    background: rgba(0,0,0,.4);
    border-radius: 8px;
    padding: 8px;
    font-size: 0.85rem;
    align-items: center;
    align-self: start;
}
#scoreboard h2 { font-size: 0.9rem; }
.score-row { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.score-val { font-size: 1.4rem; font-weight: bold; color: #ffd700; }
#status-bar {
    width: 100%;
    background: rgba(0,0,0,.4);
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 0.9rem;
    display: flex;
    align-items: flex-start;
    gap: 8px;
}
#status-msg {
    flex: 1;
    max-height: 80px;
    overflow-y: auto;
    text-align: left;
    padding: 2px 4px;
}
#status-msg p { margin: 2px 0; }
.domino-bone {
    cursor: grab;
    border-radius: 4px;
    transition: transform .1s;
}
.domino-bone:not(.bone-rotated):hover { transform: scale(1.08); }
.bone-rotated { transform: rotate(90deg); }
.bone-rotated:hover { transform: rotate(90deg) scale(1.08); }
.spinner-junction {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
}
.branch-col {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
}
.area-label {
    font-size: 0.7rem;
    opacity: .7;
    text-align: center;
    margin-bottom: 2px;
}
#boneyard-area.draw-mode {
    border: 2px solid #ffd700;
    background: rgba(255, 215, 0, .15);
}
#boneyard-area.draw-mode .domino-bone {
    cursor: grab;
    outline: 2px solid #ffd700;
    border-radius: 4px;
}
#player0-hand.drop-target {
    outline: 2px dashed #ffd700;
}
#new-game-btn {
    display: none;
    margin-left: 10px;
    padding: 6px 18px;
    background: #ffd700;
    color: #000;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.9rem;
    font-weight: bold;
}
#new-game-btn:hover { background: #ffe84d; }
"""


def _check_pyscript_cdn() -> None:
    """Warn if the PyScript CDN appears unreachable (requires internet)."""
    try:
        r = httpx.head(PYSCRIPT_CSS_URL, timeout=5.0, follow_redirects=True)
        if r.status_code >= 400:
            print(
                f"Warning: PyScript CDN returned {r.status_code}. "
                "The page may not load without internet access.",
                file=sys.stderr,
            )
    except httpx.RequestError:
        print(
            "Warning: Could not reach PyScript CDN. The page requires an internet connection to load.",
            file=sys.stderr,
        )


def _add_tag(soup: BeautifulSoup, parent: Tag, tag_name: str, **attrs: str) -> Tag:
    """Create and append a new tag to parent, returning the tag."""
    tag = soup.new_tag(tag_name, attrs=attrs)
    parent.append(tag)
    return tag


def _build_head(soup: BeautifulSoup, html_tag: Tag) -> None:
    """Populate the <head> element of the game page."""
    head = _add_tag(soup, html_tag, "head")
    _add_tag(soup, head, "meta", charset="UTF-8")
    _add_tag(
        soup,
        head,
        "meta",
        name="viewport",
        content="width=device-width, initial-scale=1.0",
    )
    title = soup.new_tag("title")
    title.string = "Claussoft Dominos - Racehorse"
    head.append(title)
    _add_tag(soup, head, "link", rel="stylesheet", href=PYSCRIPT_CSS_URL)
    style = soup.new_tag("style")
    style.string = _CSS
    head.append(style)


def _build_board(soup: BeautifulSoup, body: Tag) -> None:
    """Add the game board grid (player hands, boneyard, play area, scoreboard)."""
    board = _add_tag(soup, body, "div", id="board")

    # Player 1 hand (top - computer)
    p1_div = _add_tag(soup, board, "div", id="player1-hand")
    p1_div["class"] = "player-hand"
    lbl1 = soup.new_tag("div")
    lbl1["class"] = "area-label"
    lbl1.string = "Computer's hand"
    p1_div.append(lbl1)

    # Boneyard (left column)
    by_div = _add_tag(soup, board, "div", id="boneyard-area")
    lbl_by = soup.new_tag("div")
    lbl_by["class"] = "area-label"
    lbl_by.string = "Boneyard"
    by_div.append(lbl_by)

    # Play area (centre)
    _add_tag(soup, board, "div", id="play-area")

    # Scoreboard (right column)
    sb = _add_tag(soup, board, "div", id="scoreboard")
    h2 = soup.new_tag("h2")
    h2.string = "Score"
    sb.append(h2)
    for player, label in ((0, "You"), (1, "CPU")):
        row = soup.new_tag("div")
        row["class"] = "score-row"
        lbl = soup.new_tag("span")
        lbl.string = label
        val = soup.new_tag("span")
        val["class"] = "score-val"
        val["id"] = f"score-p{player}"
        val.string = "0"
        row.append(lbl)
        row.append(val)
        sb.append(row)

    # Player 0 hand (bottom - human)
    p0_div = _add_tag(soup, board, "div", id="player0-hand")
    p0_div["class"] = "player-hand"
    lbl0 = soup.new_tag("div")
    lbl0["class"] = "area-label"
    lbl0.string = "Your hand (drag a bone to the play area)"
    p0_div.append(lbl0)


def build_html(state: GameState) -> str:
    """Build the complete HTML page as a string using BeautifulSoup."""
    soup = BeautifulSoup("<!DOCTYPE html><html lang='en'></html>", "html.parser")
    html_tag = soup.find("html")

    _build_head(soup, html_tag)

    body = _add_tag(soup, html_tag, "body")
    h1 = soup.new_tag("h1")
    h1.string = "Claussoft Dominos - Racehorse"
    body.append(h1)

    _build_board(soup, body)

    # Status bar (scrollable message history)
    status = _add_tag(soup, body, "div", id="status-bar")
    msg_div = soup.new_tag("div")
    msg_div["id"] = "status-msg"
    p_tag = soup.new_tag("p")
    p_tag.string = state.message
    msg_div.append(p_tag)
    status.append(msg_div)
    new_game_btn = soup.new_tag("button")
    new_game_btn["id"] = "new-game-btn"
    new_game_btn.string = "New Game"
    status.append(new_game_btn)

    # Embedded game-state JSON (hidden)
    data_script = soup.new_tag("script")
    data_script["id"] = "game-state-data"
    data_script["type"] = "application/json"
    data_script.string = state.model_dump_json()
    body.append(data_script)

    # PyScript runtime
    _add_tag(soup, body, "script", type="module", src=PYSCRIPT_JS_URL)

    # Embedded Python game logic
    py_script = soup.new_tag("script", type="py")
    py_script.string = _PYSCRIPT_CODE
    body.append(py_script)

    return str(soup)


def main() -> None:
    """Generate the game HTML and open it in the default web browser."""
    _check_pyscript_cdn()
    state = deal_game()
    html = build_html(state)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as fh:
        fh.write(html)
        html_path = Path(fh.name)
    print(f"Opening {html_path}")
    webbrowser.open(html_path.as_uri())


if __name__ == "__main__":
    main()
