#!/usr/bin/env -S uv run --script

"""
Running this script opens a PyScript-based graphical user interface for
playing racehorse dominoes in the local web browser.

The game board looks similar to images/tkDomino.py.png but uses PyScript
instead of tkinter.  Dominoes are SVG images from images/dominoes_faceup/.
Each player is dealt 7 random dominoes shown in boxes at the top and bottom.
The remaining dominoes are placed face-down in the boneyard on the left.
The first player can drag a domino from their hand into the play area.
"""

# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "beautifulsoup4",
#     "httpx",
#     "pillow",
#     "pydantic",
# ]
# ///

import base64
import io
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


class GameState(BaseModel):
    """Pydantic model capturing a complete racehorse dominoes game state."""

    player0_hand: list[list[int]]  # human player (shown at bottom)
    player1_hand: list[list[int]]  # computer player (shown at top)
    boneyard: list[list[int]]  # bones not yet dealt, shown face-down
    played_dominoes: list[list[int]] = []
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


def _load_domino_image_uris() -> dict[str, str]:
    """Load all 28 domino SVG images and return them as base64 data URIs.

    Keys are of the form "a_b" where a <= b (e.g. "3_4" for the [3,4] domino).
    Values are data URIs suitable for use as SVG <image href="...">.
    """
    imgs_dir = Path(__file__).parent.parent / "images" / "dominoes_faceup"
    uris: dict[str, str] = {}
    for i in range(7):
        for j in range(i, 7):
            key = f"{i}_{j}"
            svg_path = imgs_dir / f"domino_{key}.svg"
            if svg_path.exists():
                b64 = base64.b64encode(svg_path.read_bytes()).decode("ascii")
                uris[key] = f"data:image/svg+xml;base64,{b64}"
    return uris


def _load_facedown_image_uri() -> str:
    """Load, compress, and return the face-down domino image as a JPEG data URI.

    The source image (images/dominoes_facedown/*.png) can be very large; it is
    resized to 200x400 px and saved as JPEG quality=80 before embedding so the
    generated HTML stays fast to load.  Returns an empty string if Pillow is not
    installed or no image file is found.
    """
    facedown_dir = Path(__file__).parent.parent / "images" / "dominoes_facedown"
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError:
        return ""
    for ext in ("*.png", "*.jpg", "*.jpeg"):
        for img_path in sorted(facedown_dir.glob(ext)):
            img = Image.open(img_path).convert("RGB")
            img = img.resize((200, 400), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/jpeg;base64,{b64}"
    return ""


def make_domino_svg(top: int, bottom: int, *, w: int = 55, face_down: bool = False) -> str:
    """Return an SVG string for one domino bone using pre-made image files.

    For face-up bones, uses the SVG images in images/dominoes_faceup/.
    For face-down bones, uses the compressed image from images/dominoes_facedown/.
    The whole image is rotated when the pip order requires it; individual halves
    are never rotated independently.

    Args:
        top: pip count for the top half (0-6).
        bottom: pip count for the bottom half (0-6).
        w: width of each half in pixels; the full bone is w x (2*w).
        face_down: when True the bone is rendered using the face-down skin image.
    """
    h, pad = w * 2, 3
    tw, th = w + 2 * pad, h + 2 * pad
    if face_down:
        uri = _load_facedown_image_uri()
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw}" height="{th}">'
            f'<image href="{uri}" width="{tw}" height="{th}"/>'
            f"</svg>"
        )
    uris = _load_domino_image_uris()
    a, b = (top, bottom) if top <= bottom else (bottom, top)
    uri = uris.get(f"{a}_{b}", "")
    if top > bottom:
        cx, cy = tw / 2, th / 2
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw}" height="{th}">'
            f'<image href="{uri}" width="{tw}" height="{th}" '
            f'transform="rotate(180, {cx:.1f}, {cy:.1f})"/>'
            f"</svg>"
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw}" height="{th}">'
        f'<image href="{uri}" width="{tw}" height="{th}"/>'
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
_BONE_GAP_PX = 4          # uniform gap (px) between adjacent dominoes in every direction
_COMPUTER_PLAY_DELAY_MS = 1200  # ms delay before computer plays


def _domino_svg(top, bottom, w=55, face_down=False):
    # Portrait SVG using the pre-loaded domino image.
    # face_down: use the face-down skin; otherwise look up the face-up SVG image.
    # top > bottom: rotate the whole image 180 deg so the correct half is on top.
    h, pad = w * 2, 3
    tw, th = w + 2 * pad, h + 2 * pad
    if face_down:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw}" height="{th}">'
            f'<image href="{_FACEDOWN_IMAGE_URI}" width="{tw}" height="{th}"/>'
            f'</svg>'
        )
    a, b = (top, bottom) if top <= bottom else (bottom, top)
    uri = _DOMINO_IMAGE_URIS.get(f"{a}_{b}", "")
    if top > bottom:
        cx, cy = tw / 2, th / 2
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw}" height="{th}">'
            f'<image href="{uri}" width="{tw}" height="{th}" '
            f'transform="rotate(180, {cx:.1f}, {cy:.1f})"/>'
            f'</svg>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw}" height="{th}">'
        f'<image href="{uri}" width="{tw}" height="{th}"/>'
        f'</svg>'
    )


def _domino_svg_h(top, bottom, w=55, face_down=False):
    # Landscape SVG by rotating the portrait domino image as a whole.
    # top <= bottom: CCW -90 deg (translate(0,pw) rotate(-90)) -- top pips on left.
    # top > bottom:  CW  +90 deg (translate(ph,0) rotate(90))  -- top pips on left.
    h, pad = w * 2, 3
    tw, th = h + 2 * pad, w + 2 * pad   # landscape output dimensions
    pw, ph = w + 2 * pad, h + 2 * pad   # portrait image dimensions
    if face_down:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw}" height="{th}">'
            f'<image href="{_FACEDOWN_IMAGE_URI}" width="{pw}" height="{ph}" '
            f'transform="translate(0, {pw}) rotate(-90)"/>'
            f'</svg>'
        )
    a, b = (top, bottom) if top <= bottom else (bottom, top)
    uri = _DOMINO_IMAGE_URIS.get(f"{a}_{b}", "")
    if top > bottom:
        # CW rotation: portrait-bottom ('top' pips in file) maps to landscape-left
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw}" height="{th}">'
            f'<image href="{uri}" width="{pw}" height="{ph}" '
            f'transform="translate({ph}, 0) rotate(90)"/>'
            f'</svg>'
        )
    # CCW rotation: portrait-top ('a' pips) maps to landscape-left
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw}" height="{th}">'
        f'<image href="{uri}" width="{pw}" height="{ph}" '
        f'transform="translate(0, {pw}) rotate(-90)"/>'
        f'</svg>'
    )


# ---------------------------------------------------------------------------
# Board data structures
# ---------------------------------------------------------------------------
class PlayedDomino:
    \"\"\"One placed domino; value[0] faces left/up, value[1] faces right/down.
    Regular dominoes have at most 2 active neighbor slots (left + right).
    Doubles expose all 4 slots once both horizontal sides are filled.
    \"\"\"
    def __init__(self, a, b):
        self.value = [a, b]
        self.left = None   # PlayedDomino | None
        self.right = None  # PlayedDomino | None
        self.up = None     # PlayedDomino | None (doubles only)
        self.down = None   # PlayedDomino | None (doubles only)

    @property
    def is_double(self):
        return self.value[0] == self.value[1]

    def pip_at(self, direction):
        \"\"\"Pip value exposed at the given direction.\"\"\"
        if self.is_double:
            return self.value[0]
        return self.value[0] if direction in ("left", "up") else self.value[1]

    def open_directions(self):
        \"\"\"Directions where a new bone can be attached.\"\"\"
        dirs = []
        if self.left is None:
            dirs.append("left")
        if self.right is None:
            dirs.append("right")
        # Doubles expose up/down only after both horizontal sides are connected.
        if self.is_double and self.left is not None and self.right is not None:
            if self.up is None:
                dirs.append("up")
            if self.down is None:
                dirs.append("down")
        return dirs


class PlayedDominoes:
    \"\"\"Board state as a linked tree of PlayedDomino nodes.\"\"\"

    def __init__(self):
        self.first_played_domino = None   # PlayedDomino | None

    def clear(self):
        self.first_played_domino = None

    def is_empty(self):
        return self.first_played_domino is None

    def all_bones(self):
        \"\"\"BFS over all placed bones.\"\"\"
        if not self.first_played_domino:
            return []
        result, stack, seen = [], [self.first_played_domino], set()
        while stack:
            b = stack.pop()
            bid = id(b)
            if bid in seen:
                continue
            seen.add(bid)
            result.append(b)
            for n in (b.left, b.right, b.up, b.down):
                if n is not None and id(n) not in seen:
                    stack.append(n)
        return result

    def horizontal_run(self):
        \"\"\"Left-to-right spine of the board.\"\"\"
        if not self.first_played_domino:
            return []
        cur = self.first_played_domino
        while cur.left is not None:
            cur = cur.left
        run = []
        while cur is not None:
            run.append(cur)
            cur = cur.right
        return run

    def open_ends(self):
        \"\"\"All open attachment points: list of (PlayedDomino, direction) pairs.\"\"\"
        return [(b, d) for b in self.all_bones() for d in b.open_directions()]

    def playable_pips(self):
        \"\"\"Set of pip values that can be played; None if board is empty.\"\"\"
        if not self.first_played_domino:
            return None
        return {b.pip_at(d) for b, d in self.open_ends()}

    def score(self):
        \"\"\"Sum of all open-end pip values; doubles count twice per open end.\"\"\"
        if not self.first_played_domino:
            return 0
        run = self.horizontal_run()
        # Lone double (not yet surrounded): count both halves.
        if len(run) == 1 and run[0].is_double and run[0].left is None and run[0].right is None:
            return run[0].value[0] * 2
        return sum(b.pip_at(d) * (2 if b.is_double else 1) for b, d in self.open_ends())

    def can_play(self, a, b):
        if not self.first_played_domino:
            return True
        pips = self.playable_pips()
        return a in pips or b in pips

    def play_options(self, a, b):
        \"\"\"Valid (PlayedDomino, direction) pairs for placing bone [a, b].\"\"\"
        if not self.first_played_domino:
            return []
        return [(bone, d) for bone, d in self.open_ends() if a == bone.pip_at(d) or b == bone.pip_at(d)]

    def apply_play(self, a, b, target_bone=None, target_direction=None):
        \"\"\"Place bone [a, b] onto the board. Returns the new PlayedDomino or None.\"\"\"
        if not self.first_played_domino:
            new_bone = PlayedDomino(a, b)
            self.first_played_domino = new_bone
            return new_bone
        opts = self.play_options(a, b)
        if not opts:
            return None
        if target_bone is not None and target_direction is not None:
            if (target_bone, target_direction) not in opts:
                return None
            cb, cd = target_bone, target_direction
        elif len(opts) == 1:
            cb, cd = opts[0]
        else:
            return None  # ambiguous
        pip_at = cb.pip_at(cd)
        if cd in ("left", "up"):
            new_bone = PlayedDomino(a, b) if b == pip_at else PlayedDomino(b, a)
        else:
            new_bone = PlayedDomino(a, b) if a == pip_at else PlayedDomino(b, a)
        if cd == "left":
            cb.left = new_bone
            new_bone.right = cb
        elif cd == "right":
            cb.right = new_bone
            new_bone.left = cb
        elif cd == "up":
            cb.up = new_bone
            new_bone.down = cb
        else:
            cb.down = new_bone
            new_bone.up = cb
        return new_bone

    def find_double_in_run(self, pip_val):
        \"\"\"Find the double bone with the given pip value in the horizontal run.\"\"\"
        for b in self.horizontal_run():
            if b.is_double and b.value[0] == pip_val:
                return b
        return None

    def find_tip(self, double_bone, direction):
        \"\"\"Follow the chain from double_bone in direction, return the tip bone.\"\"\"
        cur = double_bone
        while getattr(cur, direction) is not None:
            cur = getattr(cur, direction)
        return cur


# ---------------------------------------------------------------------------
# Game state (mutable; starts from the JSON embedded by the host script)
# ---------------------------------------------------------------------------
_raw = json.loads(document.getElementById("game-state-data").textContent)
_hand0 = [list(t) for t in _raw["player0_hand"]]   # human hand
_hand1 = [list(t) for t in _raw["player1_hand"]]   # computer hand
_boneyard = [list(t) for t in _raw["boneyard"]]
# Load domino face-up SVG images and the face-down skin image embedded by the host
_DOMINO_IMAGE_URIS = json.loads(document.getElementById("domino-image-uris").textContent)
_FACEDOWN_IMAGE_URI = json.loads(document.getElementById("facedown-image-uri").textContent)
_played_dominoes = PlayedDominoes()   # board state; PlayedDomino tree
_scores = [0, 0]
_current_player = 0            # 0 = human, 1 = computer
_needs_boneyard_draw = False   # True when human must draw from boneyard
_game_over = False             # True when the match has been won
_consecutive_passes = 0        # tracks back-to-back passes; game stuck when >= 2
_game_num = _raw.get("game_num", 0)  # how many hands dealt so far (first player alternates)


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
    div.className += " bone-rotated"
    hw = w // 2
    div.style.marginTop = f"{hw}px"
    div.style.marginBottom = f"{hw}px"
    div.style.marginLeft = f"-{hw}px"
    div.style.marginRight = f"-{hw}px"


def _get_branch_chain(double_bone, direction):
    \"\"\"Return the list of bones in the up or down chain from double_bone.\"\"\"
    chain = []
    cur = getattr(double_bone, direction)
    while cur is not None:
        chain.append(cur)
        cur = getattr(cur, direction)
    return chain


def _render_played_linear(area, bone, w):
    \"\"\"Render a single non-junction bone into the play area.\"\"\"
    is_double = bone.is_double
    div = _make_bone_div(bone.value[0], bone.value[1], horizontal=True, w=w)
    if is_double:
        _apply_bone_rotation(div, w)
    if bone.left is None:
        div.setAttribute("data-play-end", "left")
        div.addEventListener("dragover", ffi.create_proxy(_on_dragover))
        div.addEventListener("drop", ffi.create_proxy(_on_drop_played_bone))
    if bone.right is None:
        div.setAttribute("data-play-end", "right")
        div.addEventListener("dragover", ffi.create_proxy(_on_dragover))
        div.addEventListener("drop", ffi.create_proxy(_on_drop_played_bone))
    area.appendChild(div)


def _render_played_cross(area, double_bone, w):
    \"\"\"Render a junction for a double with up/down branches.\"\"\"
    up_chain = _get_branch_chain(double_bone, "up")
    down_chain = _get_branch_chain(double_bone, "down")
    dv = str(double_bone.value[0])

    junc = document.createElement("div")
    junc.className = "spinner-junction"

    bone_h = 2 * w + 6 + _BONE_GAP_PX
    max_branch_h = max(len(up_chain), len(down_chain)) * bone_h

    top_col = document.createElement("div")
    top_col.className = "branch-col"
    top_col.style.minHeight = f"{max_branch_h}px"
    top_col.style.justifyContent = "flex-end"
    if up_chain:
        for b in reversed(up_chain):
            is_dbl = b.is_double
            bd = _make_bone_div(b.value[0], b.value[1], horizontal=is_dbl, w=w)
            top_col.appendChild(bd)
        fc = top_col.firstChild
        fc.setAttribute("data-play-end", "up")
        fc.setAttribute("data-branch-double-val", dv)
        fc.addEventListener("dragover", ffi.create_proxy(_on_dragover))
        fc.addEventListener("drop", ffi.create_proxy(_on_drop_played_bone))
    junc.appendChild(top_col)

    sp_div = _make_bone_div(double_bone.value[0], double_bone.value[1], w=w)
    sp_div.setAttribute("data-play-end", "double")
    sp_div.setAttribute("data-double-val", dv)
    sp_div.addEventListener("dragover", ffi.create_proxy(_on_dragover))
    sp_div.addEventListener("drop", ffi.create_proxy(_on_drop_spinner_bone))
    junc.appendChild(sp_div)

    bot_col = document.createElement("div")
    bot_col.className = "branch-col"
    bot_col.style.minHeight = f"{max_branch_h}px"
    if down_chain:
        for b in down_chain:
            is_dbl = b.is_double
            bd = _make_bone_div(b.value[0], b.value[1], horizontal=is_dbl, w=w)
            bot_col.appendChild(bd)
        lc = bot_col.lastChild
        lc.setAttribute("data-play-end", "down")
        lc.setAttribute("data-branch-double-val", dv)
        lc.addEventListener("dragover", ffi.create_proxy(_on_dragover))
        lc.addEventListener("drop", ffi.create_proxy(_on_drop_played_bone))
    junc.appendChild(bot_col)

    area.appendChild(junc)


def _render_play_area():
    area = document.getElementById("play-area")
    area.innerHTML = ""
    if _played_dominoes.is_empty():
        return
    w = _compute_bone_size()
    run = _played_dominoes.horizontal_run()
    for bone in run:
        has_junction = (bone.is_double and bone.left is not None and bone.right is not None)
        if has_junction:
            _render_played_cross(area, bone, w)
        else:
            _render_played_linear(area, bone, w)


def _render_scores():
    document.getElementById("score-p0").textContent = str(_scores[0])
    document.getElementById("score-p1").textContent = str(_scores[1])
    pips = _played_dominoes.playable_pips()
    pip_el = document.getElementById("playable-pips")
    if pip_el:
        if pips is None:
            pip_el.textContent = "Open: (any)"
        else:
            pip_el.textContent = f"Open: {tuple(sorted(pips))}"
    score_el = document.getElementById("board-score")
    if score_el:
        score_el.textContent = f"Score: {_played_dominoes.score()}"
    can_play_el = document.getElementById("can-play")
    if can_play_el:
        playable = [b for b in _hand0 if _can_play(b[0], b[1])]
        can_play_el.textContent = f"Can play: {len(playable)} of {len(_hand0)}"
    opts_el = document.getElementById("play-options")
    if opts_el:
        all_dirs = {d for b in _hand0 for _, d in _played_dominoes.play_options(b[0], b[1])}
        opts_el.textContent = f"Options: {sorted(all_dirs)}" if all_dirs else "Options: (first play)"


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


def _score_played():
    s = _played_dominoes.score()
    return s if s % _SCORING_DIVISOR == 0 else 0


def _simulate_score_after_play(bone):
    # Return the best possible score after playing this bone on any valid end.
    a, b = bone[0], bone[1]
    if _played_dominoes.is_empty():
        total = a * 2 if a == b else a + b
        return total if total % _SCORING_DIVISOR == 0 else 0
    best = 0
    for tb, td in _played_dominoes.play_options(a, b):
        # Temporarily apply the play, score, then undo.
        nb = _played_dominoes.apply_play(a, b, target_bone=tb, target_direction=td)
        if nb is not None:
            s = _played_dominoes.score()
            sc = s if s % _SCORING_DIVISOR == 0 else 0
            best = max(best, sc)
            # Undo the play by unlinking the new bone.
            if td == "left":
                tb.left = None
                nb.right = None
            elif td == "right":
                tb.right = None
                nb.left = None
            elif td == "up":
                tb.up = None
                nb.down = None
            else:
                tb.down = None
                nb.up = None
    return best


def _find_bone(hand, top, bottom):
    for bone in hand:
        if bone == [top, bottom] or bone == [bottom, top]:
            return bone
    return None


def _can_play(top, bottom):
    return _played_dominoes.can_play(top, bottom)


def _valid_plays(hand):
    return [t for t in hand if _can_play(t[0], t[1])]


def _is_ambiguous_play(top, bottom):
    # Return True when the bone fits more than one placement position.
    return len(_played_dominoes.play_options(top, bottom)) > 1


def _apply_play(top, bottom, hand, target_end=None):
    bone = _find_bone(hand, top, bottom)
    if bone is None:
        return False
    run = _played_dominoes.horizontal_run()
    if target_end is not None and run:
        if target_end == "left":
            tb, td = run[0], "left"
        elif target_end == "right":
            tb, td = run[-1], "right"
        elif target_end in ("up", "down"):
            tb, td = None, None
            for bo, d in _played_dominoes.open_ends():
                if d == target_end:
                    tb, td = bo, d
                    break
            if tb is None:
                return False
        else:
            return False
        nb = _played_dominoes.apply_play(top, bottom, target_bone=tb, target_direction=td)
        if nb:
            hand.remove(bone)
            return True
        return False
    nb = _played_dominoes.apply_play(top, bottom)
    if nb:
        hand.remove(bone)
        return True
    return False


def _play_options(top, bottom):
    \"\"\"Return list of direction strings for valid plays of bone [top, bottom].\"\"\"
    if _played_dominoes.is_empty():
        return []
    opts = []
    seen = set()
    for _, d in _played_dominoes.play_options(top, bottom):
        if d not in seen:
            seen.add(d)
            opts.append(d)
    return opts


def _compute_bone_size():
    if _played_dominoes.is_empty():
        return 55
    run = _played_dominoes.horizontal_run()
    area = document.getElementById("play-area")
    avail = int(area.clientWidth) - 20
    if avail <= 50:
        avail = 650
    n = len(run)
    h_bones = sum(1 for b in run if not b.is_double)
    v_bones = n - h_bones
    gaps = max(0, n - 1) * _BONE_GAP_PX
    coeff = 2 * h_bones + v_bones
    if coeff <= 0:
        return 55
    w = (avail - 6 * n - gaps) / coeff
    # Height constraint for doubles with up/down branches.
    all_branch_depths = [
        max(
            sum(1 for _ in _get_branch_chain(b, "up")),
            sum(1 for _ in _get_branch_chain(b, "down")),
        )
        for b in run
        if b.is_double and (b.up is not None or b.down is not None)
    ]
    max_b = max(all_branch_depths, default=0)
    if max_b > 0:
        win_h = int(document.documentElement.clientHeight)
        avail_h = win_h - 280
        if avail_h > 60:
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
        window.playDominoSound("win")
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
    global _hand0, _hand1, _boneyard
    global _current_player, _needs_boneyard_draw, _consecutive_passes, _game_num
    bones = [[i, j] for i in range(7) for j in range(i, 7)]
    random.shuffle(bones)
    _hand0 = [list(t) for t in bones[:7]]
    _hand1 = [list(t) for t in bones[7:14]]
    _boneyard = [list(t) for t in bones[14:]]
    _played_dominoes.clear()
    _game_num += 1
    _needs_boneyard_draw = False
    _consecutive_passes = 0
    window.playDominoSound("deal")
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
# Turn management
# ---------------------------------------------------------------------------
def _start_turn(player_idx, prefix=""):
    global _current_player, _needs_boneyard_draw, _consecutive_passes
    _current_player = player_idx
    _needs_boneyard_draw = False
    hand = _hand0 if player_idx == 0 else _hand1
    if _valid_plays(hand):
        _render_all()
        if player_idx == 1:
            _set_message(prefix + "Computer is thinking...")
            def _delayed_play(*_):
                _computer_play()
            window.setTimeout(ffi.create_proxy(_delayed_play), _COMPUTER_PLAY_DELAY_MS)
        else:
            _set_message(prefix + "Your turn: drag a domino to the play area.")
    elif len(_boneyard) > _BONEYARD_MIN:
        if player_idx == 1:
            _render_all()
            _set_message(prefix + "Computer draws from boneyard...")
            def _delayed_draw(*_):
                _computer_draw_and_play()
            window.setTimeout(ffi.create_proxy(_delayed_draw), _COMPUTER_PLAY_DELAY_MS)
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
    pts = _score_played()
    scored = pts > 0
    is_dbl = _is_double(bone_played)
    if scored:
        _scores[player_idx] += pts // _SCORING_DIVISOR
        window.playDominoSound("score")
    else:
        window.playDominoSound("play")
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
        window.playDominoSound("draw")
    _render_all()
    if drawn_count:
        draw_msg = f"Computer drew {drawn_count} bone(s) from the boneyard. "
    else:
        draw_msg = ""
    if _valid_plays(_hand1):
        _set_message(draw_msg + "Computer's turn...")
        def _delayed_play2(*_):
            _computer_play()
        window.setTimeout(ffi.create_proxy(_delayed_play2), _COMPUTER_PLAY_DELAY_MS)
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
            _simulate_score_after_play(t),
            _is_double(t),
            t[0] + t[1],
        ),
    )
    opts = _play_options(best[0], best[1]) if not _played_dominoes.is_empty() else []
    tgt = opts[0] if opts else None
    if len(opts) > 1:
        a, b = best[0], best[1]
        best_sc = -1
        for o in opts:
            run = _played_dominoes.horizontal_run()
            if o == "left":
                tb, td = run[0], "left"
            elif o == "right":
                tb, td = run[-1], "right"
            else:
                tb, td = None, None
                for bo, d in _played_dominoes.open_ends():
                    if d == o:
                        tb, td = bo, d
                        break
            if tb is None:
                continue
            nb = _played_dominoes.apply_play(a, b, target_bone=tb, target_direction=td)
            if nb is not None:
                s = _played_dominoes.score()
                sc = s if s % _SCORING_DIVISOR == 0 else 0
                # Undo
                if td == "left":
                    tb.left = None
                    nb.right = None
                elif td == "right":
                    tb.right = None
                    nb.left = None
                elif td == "up":
                    tb.up = None
                    nb.down = None
                else:
                    tb.down = None
                    nb.up = None
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
    # If the drop landed on a played-bone end or spinner bone, that element's dedicated
    # handler takes priority (guards against stopPropagation not firing through proxies).
    if event.target.closest("[data-play-end]"):
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
    sp_opts = [o for o in opts if o in ("up", "down")]
    # Bone only fits the spinner branches - guide player to drop on the double bone.
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
    event.preventDefault()
    event.stopPropagation()
    if _current_player != 0 or _needs_boneyard_draw or _game_over:
        return
    data = event.dataTransfer.getData("text/plain")
    if data.startswith("boneyard:"):
        return
    top_s, bottom_s = data.split(",")
    top, bottom = int(top_s), int(bottom_s)
    dv = int(event.currentTarget.getAttribute("data-double-val"))
    db = _played_dominoes.find_double_in_run(dv)
    if db is None:
        return
    offset_y = event.offsetY
    el_h = event.currentTarget.offsetHeight
    target_direction = "up" if offset_y < el_h / 2 else "down"
    if not _played_dominoes.can_play(top, bottom):
        _set_message(f"[{top}|{bottom}] cannot be played here - try another bone.")
        return
    tb = _played_dominoes.find_tip(db, target_direction)
    new_bone = _played_dominoes.apply_play(top, bottom, target_bone=tb, target_direction=target_direction)
    if new_bone:
        bone = _find_bone(_hand0, top, bottom)
        _hand0.remove(bone)
        _after_play(0, [top, bottom])
    else:
        half = "top" if target_direction == "up" else "bottom"
        _set_message(
            f"[{top}|{bottom}] does not fit the {half} branch. "
            f"Try dropping on the other half of the double."
        )


def _on_drop_played_bone(event):
    event.preventDefault()
    event.stopPropagation()
    if _current_player != 0 or _needs_boneyard_draw or _game_over:
        return
    chain_end = event.currentTarget.getAttribute("data-play-end")
    if not chain_end:
        return
    data = event.dataTransfer.getData("text/plain")
    if data.startswith("boneyard:"):
        return
    top_s, bottom_s = data.split(",")
    top, bottom = int(top_s), int(bottom_s)
    if not _played_dominoes.can_play(top, bottom):
        _set_message(f"[{top}|{bottom}] cannot be played here - try another bone.")
        return
    run = _played_dominoes.horizontal_run()
    if chain_end == "left":
        tb, td = run[0], "left"
    elif chain_end == "right":
        tb, td = run[-1], "right"
    elif chain_end in ("up", "down"):
        dv = int(event.currentTarget.getAttribute("data-branch-double-val"))
        db = _played_dominoes.find_double_in_run(dv)
        if db is None:
            return
        tb = _played_dominoes.find_tip(db, chain_end)
        td = chain_end
    else:
        return
    if _played_dominoes.apply_play(top, bottom, target_bone=tb, target_direction=td):
        bone = _find_bone(_hand0, top, bottom)
        _hand0.remove(bone)
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
    window.playDominoSound("draw")
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
    title.string = "Claussoft Dominoes - Racehorse"
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

    pip_div = soup.new_tag("div")
    pip_div["id"] = "playable-pips"
    pip_div["style"] = "font-size: 0.75rem; opacity: 0.8; text-align: center;"
    sb.append(pip_div)

    for el_id in ("board-score", "can-play", "play-options"):
        el = soup.new_tag("div")
        el["id"] = el_id
        el["style"] = "font-size: 0.75rem; opacity: 0.8; text-align: center;"
        sb.append(el)

    # Player 0 hand (bottom - human)
    p0_div = _add_tag(soup, board, "div", id="player0-hand")
    p0_div["class"] = "player-hand"
    lbl0 = soup.new_tag("div")
    lbl0["class"] = "area-label"
    lbl0.string = "Your hand (drag a bone to the play area)"
    p0_div.append(lbl0)


def build_html(state: GameState) -> str:
    """Build the complete HTML page as a string using BeautifulSoup."""
    import json as _json  # noqa: PLC0415

    soup = BeautifulSoup("<!DOCTYPE html><html lang='en'></html>", "html.parser")
    html_tag = soup.find("html")

    _build_head(soup, html_tag)

    body = _add_tag(soup, html_tag, "body")
    h1 = soup.new_tag("h1")
    h1.string = "Claussoft Dominoes - Racehorse"
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

    # Embedded domino face-up SVG image URIs (loaded at PyScript startup)
    img_uris_script = soup.new_tag("script")
    img_uris_script["id"] = "domino-image-uris"
    img_uris_script["type"] = "application/json"
    img_uris_script.string = _json.dumps(_load_domino_image_uris())
    body.append(img_uris_script)

    # Embedded face-down domino skin image URI (loaded at PyScript startup)
    facedown_script = soup.new_tag("script")
    facedown_script["id"] = "facedown-image-uri"
    facedown_script["type"] = "application/json"
    facedown_script.string = _json.dumps(_load_facedown_image_uri())
    body.append(facedown_script)

    # JavaScript sound function
    js_script = soup.new_tag("script")
    js_script.string = """
function playDominoSound(type) {
    try {
        var ctx = new (window.AudioContext || window.webkitAudioContext)();
        var o = ctx.createOscillator();
        var g = ctx.createGain();
        o.connect(g);
        g.connect(ctx.destination);
        var freq = {"play": 440, "score": 660, "deal": 330, "win": 880, "draw": 220}[type] || 440;
        o.frequency.value = freq;
        g.gain.setValueAtTime(0.3, ctx.currentTime);
        g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
        o.start(ctx.currentTime);
        o.stop(ctx.currentTime + 0.3);
    } catch(e) {}
}
"""
    body.append(js_script)

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
