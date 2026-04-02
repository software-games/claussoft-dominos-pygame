#!/usr/bin/env -S uv run --script

"""
Running this script opens a PyGame-CE-based graphical user interface for
playing racehorse dominoes.

Dominoes are drawn programmatically using pygame.draw primitives.
Face-down tiles use skin images from images/dominoes_facedown/ when Pillow
is available.  Click a bone in your hand to select it, then click a green
arrow in the play area to place it.
"""

# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pillow",
#     "pydantic",
#     "pygame-ce",
# ]
# ///

import random
from pathlib import Path

import pygame
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Game constants
# ---------------------------------------------------------------------------
_SCORING_DIVISOR = 5  # racehorse: a point for every 5 pips
_WIN_SCORE = 30  # first player to reach this score wins the match
_BONEYARD_MIN = 2  # must leave at least this many bones in the boneyard
_BONE_GAP_PX = 4  # uniform gap (px) between adjacent dominoes
_COMPUTER_PLAY_DELAY_MS = 1200  # ms delay before the computer plays

# ---------------------------------------------------------------------------
# PyGame display constants
# ---------------------------------------------------------------------------
WINDOW_W = 1200
WINDOW_H = 800
FPS = 30
HEADER_H = 36
CPU_HAND_H = 114
PLAYER_HAND_H = 114
STATUS_H = 84
BONEYARD_W = 148
SCORE_W = 158
GAP = 6
BONE_W = 40  # half-size (px) used for domino surfaces

BG_COLOR: tuple[int, int, int] = (45, 90, 27)
BONE_FG: tuple[int, int, int] = (245, 235, 210)
BONE_BORDER: tuple[int, int, int] = (30, 30, 30)
PIP_COLOR: tuple[int, int, int] = (20, 20, 20)
DIVIDER_COLOR: tuple[int, int, int] = (80, 80, 80)
TEXT_COLOR: tuple[int, int, int] = (255, 255, 255)
GOLD_COLOR: tuple[int, int, int] = (255, 215, 0)
SELECTED_OUTLINE: tuple[int, int, int] = (255, 215, 0)
DROP_ZONE_COLOR: tuple[int, int, int] = (0, 200, 100)
FACEDOWN_BG: tuple[int, int, int] = (55, 85, 140)
FACEDOWN_STRIPE: tuple[int, int, int] = (70, 100, 160)
DRAW_MODE_BG: tuple[int, int, int] = (30, 70, 20)
DRAW_MODE_BORDER: tuple[int, int, int] = (255, 215, 0)

# Custom pygame user-event for computer play
_COMPUTER_PLAY_EVENT = pygame.USEREVENT + 1

# ---------------------------------------------------------------------------
# Pydantic game-state model
# ---------------------------------------------------------------------------


class GameState(BaseModel):
    """Pydantic model capturing a complete racehorse dominoes game state."""

    player0_hand: list[list[int]]  # human player (bottom)
    player1_hand: list[list[int]]  # computer player (top)
    boneyard: list[list[int]]  # face-down bones not yet dealt
    played_dominoes: list[list[int]] = []
    scores: list[int] = [0, 0]
    current_player: int = 0
    game_num: int = 0  # incremented each new hand; first_player = game_num % 2
    message: str = "Your turn: click a domino from your hand."


# ---------------------------------------------------------------------------
# Game utilities
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Board data structures (formerly in _PYSCRIPT_CODE)
# ---------------------------------------------------------------------------


class PlayedDomino:
    """One placed domino; value[0] faces left/up, value[1] faces right/down.

    Regular dominoes have at most 2 active neighbor slots (left + right).
    Doubles expose all 4 slots once both horizontal sides are filled.
    """

    def __init__(self, a: int, b: int) -> None:
        self.value = [a, b]
        self.left: PlayedDomino | None = None
        self.right: PlayedDomino | None = None
        self.up: PlayedDomino | None = None
        self.down: PlayedDomino | None = None

    @property
    def is_double(self) -> bool:
        """Return True when both pip values are equal."""
        return self.value[0] == self.value[1]

    def pip_at(self, direction: str) -> int:
        """Return the pip value exposed in the given direction."""
        if self.is_double:
            return self.value[0]
        return self.value[0] if direction in ("left", "up") else self.value[1]

    def open_directions(self) -> list[str]:
        """Return the directions where a new bone can be attached.

        Bones placed in a vertical branch (connected only via up/down pointers,
        with left and right both None) expose only their one open end direction
        (up or down).  Horizontal-run bones expose left and/or right; junction
        doubles additionally expose up/down after both horizontal sides are filled.
        """
        dirs: list[str] = []
        # Vertical branch bone: connected only through up/down, not left/right.
        if self.left is None and self.right is None and (self.up is not None or self.down is not None):
            if self.up is None:
                dirs.append("up")
            if self.down is None:
                dirs.append("down")
            return dirs
        # Horizontal-run bone.
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
    """Board state as a linked tree of PlayedDomino nodes."""

    def __init__(self) -> None:
        self.first_played_domino: PlayedDomino | None = None

    def clear(self) -> None:
        """Reset the board."""
        self.first_played_domino = None

    def is_empty(self) -> bool:
        """Return True when no bones have been played."""
        return self.first_played_domino is None

    def all_bones(self) -> list[PlayedDomino]:
        """BFS over all placed bones."""
        if not self.first_played_domino:
            return []
        result: list[PlayedDomino] = []
        stack: list[PlayedDomino] = [self.first_played_domino]
        seen: set[int] = set()
        while stack:
            b = stack.pop()
            bid = id(b)
            if bid in seen:
                continue
            seen.add(bid)
            result.append(b)
            for n in (b.left, b.right, b.up, b.down):
                if n is not None and id(n) not in seen:
                    stack.append(n)  # noqa: PERF401
        return result

    def horizontal_run(self) -> list[PlayedDomino]:
        """Return the left-to-right spine of the board."""
        if not self.first_played_domino:
            return []
        cur = self.first_played_domino
        while cur.left is not None:
            cur = cur.left
        run: list[PlayedDomino] = []
        while cur is not None:
            run.append(cur)
            cur = cur.right
        return run

    def open_ends(self) -> list[tuple[PlayedDomino, str]]:
        """Return all open attachment points as (PlayedDomino, direction) pairs."""
        return [(b, d) for b in self.all_bones() for d in b.open_directions()]

    def playable_pips(self) -> set[int] | None:
        """Return the set of pip values that can be played, or None if board is empty."""
        if not self.first_played_domino:
            return None
        return {b.pip_at(d) for b, d in self.open_ends()}

    def score(self) -> int:
        """Sum of all open-end pip values; doubles count twice per open end."""
        if not self.first_played_domino:
            return 0
        run = self.horizontal_run()
        # Lone double (not yet surrounded): count both halves.
        if len(run) == 1 and run[0].is_double and run[0].left is None and run[0].right is None:
            return run[0].value[0] * 2
        total = 0
        for b, d in self.open_ends():
            # Empty spinner (junction) vertical branches don't score until a bone
            # is placed there.  A junction has both left and right connected.
            if d in ("up", "down") and getattr(b, d) is None and b.left is not None and b.right is not None:
                continue
            total += b.pip_at(d) * (2 if b.is_double else 1)
        return total

    def can_play(self, a: int, b: int) -> bool:
        """Return True when [a, b] can be placed somewhere on the board."""
        if not self.first_played_domino:
            return True
        pips = self.playable_pips()
        return pips is not None and (a in pips or b in pips)

    def play_options(self, a: int, b: int) -> list[tuple[PlayedDomino, str]]:
        """Return valid (PlayedDomino, direction) pairs for placing bone [a, b]."""
        if not self.first_played_domino:
            return []
        return [(bone, d) for bone, d in self.open_ends() if a == bone.pip_at(d) or b == bone.pip_at(d)]

    def apply_play(
        self,
        a: int,
        b: int,
        target_bone: PlayedDomino | None = None,
        target_direction: str | None = None,
    ) -> PlayedDomino | None:
        """Place bone [a, b] onto the board. Returns the new PlayedDomino, or None."""
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

    def find_double_in_run(self, pip_val: int) -> PlayedDomino | None:
        """Find the double bone with the given pip value in the horizontal run."""
        for b in self.horizontal_run():
            if b.is_double and b.value[0] == pip_val:
                return b
        return None

    def find_tip(self, double_bone: PlayedDomino, direction: str) -> PlayedDomino:
        """Follow the chain from double_bone in direction and return the tip bone."""
        cur: PlayedDomino = double_bone
        while getattr(cur, direction) is not None:
            cur = getattr(cur, direction)
        return cur


# ---------------------------------------------------------------------------
# Branch-chain helper
# ---------------------------------------------------------------------------


def _get_branch_chain(double_bone: PlayedDomino, direction: str) -> list[PlayedDomino]:
    """Return the ordered list of bones in the up or down branch from double_bone."""
    chain: list[PlayedDomino] = []
    cur: PlayedDomino | None = getattr(double_bone, direction)
    while cur is not None:
        chain.append(cur)
        cur = getattr(cur, direction)
    return chain


# ---------------------------------------------------------------------------
# Face-down image loading (Pillow, optional)
# ---------------------------------------------------------------------------


def _load_facedown_surfaces(bone_w: int) -> dict[str, pygame.Surface]:
    """Load face-down images as portrait pygame.Surfaces sized for bone_w.

    Returns an empty dict when Pillow is unavailable or no images exist.

    Args:
        bone_w: bone half-size in pixels; portrait size is (bone_w+6) x (2*bone_w+10).
    """
    facedown_dir = Path(__file__).parent.parent / "images" / "dominoes_facedown"
    result: dict[str, pygame.Surface] = {}
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError:
        return result
    tw = bone_w + 6
    th = 2 * bone_w + 10
    for ext in ("*.png", "*.jpg", "*.jpeg"):
        for img_path in sorted(facedown_dir.glob(ext)):
            img = Image.open(img_path).convert("RGB").resize((tw, th), Image.LANCZOS)
            surf = pygame.image.frombytes(img.tobytes(), (tw, th), "RGB")
            result[img_path.stem] = surf
    return result


# ---------------------------------------------------------------------------
# PyGame domino rendering
# ---------------------------------------------------------------------------

_PIP_POSITIONS: dict[int, list[tuple[float, float]]] = {
    0: [],
    1: [(0.5, 0.5)],
    2: [(0.5, 0.25), (0.5, 0.75)],
    3: [(0.75, 0.25), (0.5, 0.5), (0.25, 0.75)],
    4: [(0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)],
    5: [(0.25, 0.25), (0.75, 0.25), (0.5, 0.5), (0.25, 0.75), (0.75, 0.75)],
    6: [(0.25, 0.2), (0.75, 0.2), (0.25, 0.5), (0.75, 0.5), (0.25, 0.8), (0.75, 0.8)],
}


def _draw_half_pips(surface: pygame.Surface, count: int, ox: int, oy: int, w: int) -> None:
    """Draw pip circles for one half of a domino at offset (ox, oy) with half-size w."""
    r = max(2, w // 8)
    for fx, fy in _PIP_POSITIONS[count]:
        pygame.draw.circle(surface, PIP_COLOR, (ox + int(fx * w), oy + int(fy * w)), r)


def _make_facedown_surface(
    w: int,
    *,
    horizontal: bool = False,
    skin: pygame.Surface | None = None,
    selected: bool = False,
) -> pygame.Surface:
    """Return a face-down domino Surface of half-size w.

    Args:
        w: bone half-size in pixels.
        horizontal: render in landscape orientation when True.
        skin: optional portrait-sized skin image to use.
        selected: draw a gold highlight border when True.
    """
    pad, div = 3, 4
    border_color = SELECTED_OUTLINE if selected else BONE_BORDER
    if horizontal:
        sw, sh = 2 * w + div + 2 * pad, w + 2 * pad
    else:
        sw, sh = w + 2 * pad, 2 * w + div + 2 * pad
    if skin is not None:
        src = pygame.transform.rotate(skin, -90) if horizontal else skin
        surf = pygame.transform.scale(src, (sw, sh))
    else:
        surf = pygame.Surface((sw, sh))
        surf.fill(FACEDOWN_BG)
        for i in range(-sh, sw, 8):
            pygame.draw.line(surf, FACEDOWN_STRIPE, (i, 0), (i + sh, sh), 1)
    pygame.draw.rect(surf, border_color, (0, 0, sw, sh), 2, border_radius=4)
    return surf


def _make_domino_surface(
    top: int,
    bottom: int,
    w: int = BONE_W,
    *,
    horizontal: bool = False,
    selected: bool = False,
) -> pygame.Surface:
    """Return a face-up domino Surface of half-size w.

    Args:
        top: pip count for the top (or left when horizontal) half.
        bottom: pip count for the bottom (or right when horizontal) half.
        w: bone half-size in pixels; portrait size is (w+6) x (2*w+10).
        horizontal: render in landscape orientation when True.
        selected: draw a gold highlight border when True.
    """
    pad, div = 3, 4
    border_color = SELECTED_OUTLINE if selected else BONE_BORDER
    if horizontal:
        sw, sh = 2 * w + div + 2 * pad, w + 2 * pad
        surf = pygame.Surface((sw, sh))
        surf.fill(BONE_FG)
        x_div = pad + w + div // 2
        pygame.draw.line(surf, DIVIDER_COLOR, (x_div, pad), (x_div, sh - pad), 2)
        _draw_half_pips(surf, top, pad, pad, w)
        _draw_half_pips(surf, bottom, pad + w + div, pad, w)
    else:
        sw, sh = w + 2 * pad, 2 * w + div + 2 * pad
        surf = pygame.Surface((sw, sh))
        surf.fill(BONE_FG)
        y_div = pad + w + div // 2
        pygame.draw.line(surf, DIVIDER_COLOR, (pad, y_div), (sw - pad, y_div), 2)
        _draw_half_pips(surf, top, pad, pad, w)
        _draw_half_pips(surf, bottom, pad, pad + w + div, w)
    pygame.draw.rect(surf, border_color, (0, 0, sw, sh), 2, border_radius=4)
    return surf


# ---------------------------------------------------------------------------
# Mutable game state (module-level globals)
# ---------------------------------------------------------------------------
_hand0: list[list[int]] = []
_hand1: list[list[int]] = []
_boneyard: list[list[int]] = []
_played_dominoes = PlayedDominoes()
_scores: list[int] = [0, 0]
_current_player: int = 0
_needs_boneyard_draw: bool = False
_game_over: bool = False
_consecutive_passes: int = 0
_game_num: int = 0
_selected_bone: list[int] | None = None
_messages: list[str] = []
_computer_must_draw: bool = False
_facedown_surfaces: dict[str, pygame.Surface] = {}
_active_facedown: pygame.Surface | None = None
_click_targets: list[tuple[pygame.Rect, str, dict[str, object]]] = []


# ---------------------------------------------------------------------------
# Game logic helpers
# ---------------------------------------------------------------------------


def _is_double(bone: list[int]) -> bool:
    return bone[0] == bone[1]


def _hand_value(hand: list[list[int]]) -> int:
    return sum(t[0] + t[1] for t in hand)


def _score_played() -> int:
    s = _played_dominoes.score()
    return s if s % _SCORING_DIVISOR == 0 else 0


def _undo_play(target_bone: PlayedDomino, direction: str, new_bone: PlayedDomino) -> None:
    """Unlink new_bone from target_bone to reverse a trial apply_play."""
    if direction == "left":
        target_bone.left = None
        new_bone.right = None
    elif direction == "right":
        target_bone.right = None
        new_bone.left = None
    elif direction == "up":
        target_bone.up = None
        new_bone.down = None
    else:
        target_bone.down = None
        new_bone.up = None


def _simulate_score_after_play(bone: list[int]) -> int:
    """Return the best possible score achievable by playing bone on any valid end."""
    a, b = bone[0], bone[1]
    if _played_dominoes.is_empty():
        total = a * 2 if a == b else a + b
        return total if total % _SCORING_DIVISOR == 0 else 0
    best = 0
    for tb, td in _played_dominoes.play_options(a, b):
        nb = _played_dominoes.apply_play(a, b, target_bone=tb, target_direction=td)
        if nb is not None:
            s = _played_dominoes.score()
            sc = s if s % _SCORING_DIVISOR == 0 else 0
            best = max(best, sc)
            _undo_play(tb, td, nb)
    return best


def _bones_match(bone: list[int], top: int, bottom: int) -> bool:
    """Return True when bone matches [top, bottom] in either orientation."""
    return bone in ([top, bottom], [bottom, top])


def _find_bone(hand: list[list[int]], top: int, bottom: int) -> list[int] | None:
    for bone in hand:
        if _bones_match(bone, top, bottom):
            return bone
    return None


def _can_play(top: int, bottom: int) -> bool:
    return _played_dominoes.can_play(top, bottom)


def _valid_plays(hand: list[list[int]]) -> list[list[int]]:
    return [t for t in hand if _can_play(t[0], t[1])]


def _play_options(top: int, bottom: int) -> list[str]:
    """Return unique direction strings for valid plays of bone [top, bottom]."""
    if _played_dominoes.is_empty():
        return []
    seen: set[str] = set()
    opts: list[str] = []
    for _, d in _played_dominoes.play_options(top, bottom):
        if d not in seen:
            seen.add(d)
            opts.append(d)
    return opts


def _compute_bone_size(area_w: int, area_h: int) -> int:
    """Return the largest bone half-size (px) that fits the play area.

    Args:
        area_w: available width of the play area in pixels.
        area_h: available height of the play area in pixels.
    """
    if _played_dominoes.is_empty():
        return BONE_W
    run = _played_dominoes.horizontal_run()
    avail = max(area_w - 20, 50)
    n = len(run)
    h_bones = sum(1 for b in run if not b.is_double)
    v_bones = n - h_bones
    gaps = max(0, n - 1) * _BONE_GAP_PX
    coeff = 2 * h_bones + v_bones
    if coeff <= 0:
        return BONE_W
    # portrait bone width = w + 6 (w + 2*pad), landscape = 2*w + 10 (2*w + div + 2*pad)
    w = (avail - 6 * v_bones - 10 * h_bones - gaps) / coeff
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
        avail_h = area_h - 40
        if avail_h > 60:
            gap = _BONE_GAP_PX
            num = avail_h - (12 + 2 * gap) * max_b - 6
            denom = 4 * max_b + 2
            if denom > 0 and num > 0:
                w = min(w, num / denom)
    return max(10, min(BONE_W, int(w)))


# ---------------------------------------------------------------------------
# Message logging
# ---------------------------------------------------------------------------


def _set_message(msg: str) -> None:
    _messages.append(msg)
    if len(_messages) > 20:
        del _messages[:-20]


# ---------------------------------------------------------------------------
# Computer play scheduling
# ---------------------------------------------------------------------------


def _schedule_computer_play(*, draw_first: bool) -> None:
    """Schedule the computer's next action via a one-shot pygame timer."""
    global _computer_must_draw
    _computer_must_draw = draw_first
    pygame.time.set_timer(_COMPUTER_PLAY_EVENT, _COMPUTER_PLAY_DELAY_MS, loops=1)


# ---------------------------------------------------------------------------
# Win / end-of-hand logic
# ---------------------------------------------------------------------------


def _check_win_after_play(player_idx: int) -> None:
    """Award bonus pts after a player clears their hand; check for match win."""
    global _game_over
    opp_hand = _hand1 if player_idx == 0 else _hand0
    bonus = _hand_value(opp_hand) // _SCORING_DIVISOR
    _scores[player_idx] += bonus
    winner_name = "You" if player_idx == 0 else "Computer"
    if _scores[player_idx] >= _WIN_SCORE:
        _game_over = True
        _set_message(
            f"{winner_name} wins the match with {_scores[player_idx]} points! "
            f"(+{bonus} pts from opponent's hand)"
        )
    else:
        _set_message(
            f"{winner_name} cleared the hand! +{bonus} bonus pts. "
            f"Scores: You {_scores[0]}, CPU {_scores[1]}. Dealing new hand..."
        )
        _deal_new_hand()


def _deal_new_hand() -> None:
    """Shuffle and deal a fresh set of bones, preserving match scores."""
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
    first_player = _game_num % 2
    first_name = "Computer" if first_player == 1 else "You"
    goes = "goes" if first_player == 1 else "go"
    _set_message(f"New hand dealt! {first_name} {goes} first.")
    _start_turn(first_player)


def _end_stuck_game() -> None:
    """Award points to the player with fewer pips when both players pass."""
    global _game_over
    v0 = _hand_value(_hand0)
    v1 = _hand_value(_hand1)
    if v0 < v1:
        winner_idx, bonus = 0, v1 // _SCORING_DIVISOR
    elif v1 < v0:
        winner_idx, bonus = 1, v0 // _SCORING_DIVISOR
    else:
        _game_over = True
        _set_message("Game stuck - both hands equal. No winner this hand.")
        return
    _scores[winner_idx] += bonus
    winner_name = "You" if winner_idx == 0 else "Computer"
    if _scores[winner_idx] >= _WIN_SCORE:
        _game_over = True
        _set_message(f"Game stuck! {winner_name} wins the match with {_scores[winner_idx]} pts!")
    else:
        _set_message(
            f"Game stuck! {winner_name} had fewer pips, gains {bonus} pts. "
            f"Scores: You {_scores[0]}, CPU {_scores[1]}. Dealing new hand..."
        )
        _deal_new_hand()


# ---------------------------------------------------------------------------
# Turn management
# ---------------------------------------------------------------------------


def _start_turn(player_idx: int, prefix: str = "") -> None:
    """Set up for a player's turn, scheduling computer moves as needed."""
    global _current_player, _needs_boneyard_draw, _consecutive_passes
    _current_player = player_idx
    _needs_boneyard_draw = False
    hand = _hand0 if player_idx == 0 else _hand1
    if _valid_plays(hand):
        if player_idx == 1:
            _set_message(prefix + "Computer is thinking...")
            _schedule_computer_play(draw_first=False)
        else:
            _set_message(prefix + "Your turn: click a domino from your hand.")
    elif len(_boneyard) > _BONEYARD_MIN:
        if player_idx == 1:
            _set_message(prefix + "Computer draws from boneyard...")
            _schedule_computer_play(draw_first=True)
        else:
            _needs_boneyard_draw = True
            _set_message(prefix + "No playable bones! Click a bone in the Boneyard to draw.")
    else:
        _consecutive_passes += 1
        if _consecutive_passes >= 2:
            _end_stuck_game()
        else:
            other = 1 - player_idx
            _set_message(
                prefix + f"{'You' if player_idx == 0 else 'Computer'} passes "
                f"(no valid bones, boneyard too small). "
                f"{'Computer' if player_idx == 0 else 'Your'} turn."
            )
            _start_turn(other)


def _after_play_hand_empty(player_idx: int, pts: int, *, scored: bool, is_dbl: bool) -> None:
    """Handle the special rules when a player just played their last bone."""
    if (scored or is_dbl) and len(_boneyard) > _BONEYARD_MIN:
        player_name = "You" if player_idx == 0 else "Computer"
        if is_dbl and scored:
            prefix = (
                f"{player_name} played a double and scored "
                f"{pts // _SCORING_DIVISOR} pt(s) with their last bone! "
                "Must draw and keep playing. "
            )
        elif is_dbl:
            prefix = f"{player_name} played their last bone (a double)! Must draw and keep playing. "
        else:
            prefix = (
                f"{player_name} scored {pts // _SCORING_DIVISOR} pt(s) "
                "with their last bone! Must draw and keep playing. "
            )
        _start_turn(player_idx, prefix=prefix)
    else:
        _check_win_after_play(player_idx)


def _after_play_go_again(player_idx: int, pts: int, *, scored: bool, is_dbl: bool) -> None:
    """Build the go-again prefix message and restart the same player's turn."""
    name = "You" if player_idx == 0 else "Computer"
    if is_dbl and scored:
        prefix = f"{name} played a double and scored {pts // _SCORING_DIVISOR} pt(s)! Go again. "
    elif is_dbl:
        prefix = f"{name} played a double! Go again. "
    else:
        prefix = f"{name} scored {pts // _SCORING_DIVISOR} pt(s)! Go again. "
    _start_turn(player_idx, prefix=prefix)


def _after_play(player_idx: int, bone_played: list[int]) -> None:
    """Handle scoring, go-again, and win after a bone is successfully placed."""
    global _consecutive_passes
    _consecutive_passes = 0
    hand = _hand0 if player_idx == 0 else _hand1
    pts = _score_played()
    scored = pts > 0
    is_dbl = _is_double(bone_played)
    if scored:
        _scores[player_idx] += pts // _SCORING_DIVISOR
    _print_board_state(player_idx, bone_played)
    if not hand:
        _after_play_hand_empty(player_idx, pts, scored=scored, is_dbl=is_dbl)
        return
    if scored or is_dbl:
        _after_play_go_again(player_idx, pts, scored=scored, is_dbl=is_dbl)
    else:
        _start_turn(1 - player_idx)


# ---------------------------------------------------------------------------
# Computer player
# ---------------------------------------------------------------------------


def _find_target_for_direction(direction: str, run: list[PlayedDomino]) -> tuple[PlayedDomino | None, str]:
    """Map a direction string to a (target_bone, direction) pair."""
    if direction == "left" and run:
        return run[0], "left"
    if direction == "right" and run:
        return run[-1], "right"
    for bo, d in _played_dominoes.open_ends():
        if d == direction:
            return bo, d
    return None, direction


def _best_direction_for(a: int, b: int, opts: list[str]) -> str:
    """Return the direction that maximises the score for placing bone [a, b]."""
    best_sc = -1
    best_tgt = opts[0]
    run = _played_dominoes.horizontal_run()
    for o in opts:
        tb, td = _find_target_for_direction(o, run)
        if tb is None:
            continue
        nb = _played_dominoes.apply_play(a, b, target_bone=tb, target_direction=td)
        if nb is not None:
            s = _played_dominoes.score()
            sc = s if s % _SCORING_DIVISOR == 0 else 0
            _undo_play(tb, td, nb)
            if sc > best_sc:
                best_sc = sc
                best_tgt = o
    return best_tgt


def _apply_play_to_hand(
    top: int,
    bottom: int,
    hand: list[list[int]],
    target_end: str | None = None,
) -> bool:
    """Place [top, bottom] from hand onto the board, removing it from hand on success.

    Args:
        top: first pip value of the bone to play.
        bottom: second pip value of the bone to play.
        hand: the player's current hand; the matching bone is removed on success.
        target_end: direction string for targeted placement.
    """
    bone = _find_bone(hand, top, bottom)
    if bone is None:
        return False
    run = _played_dominoes.horizontal_run()
    if target_end is not None and run:
        tb, td = _find_target_for_direction(target_end, run)
        if tb is None:
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


def _computer_draw_and_play() -> None:
    """Draw from the boneyard until a play is possible, then schedule a play."""
    global _consecutive_passes
    drawn_count = 0
    while not _valid_plays(_hand1) and len(_boneyard) > _BONEYARD_MIN:
        drawn = _boneyard.pop(random.randrange(len(_boneyard)))
        _hand1.append(drawn)
        drawn_count += 1
    draw_msg = f"Computer drew {drawn_count} bone(s) from the boneyard. " if drawn_count else ""
    if _valid_plays(_hand1):
        _set_message(draw_msg + "Computer's turn...")
        _schedule_computer_play(draw_first=False)
    else:
        _consecutive_passes += 1
        if _consecutive_passes >= 2:
            _end_stuck_game()
        else:
            _set_message(draw_msg + "Computer passes - no valid bones. Your turn.")
            _start_turn(0)


def _computer_play() -> None:
    """Pick and play the best available bone from the computer's hand."""
    plays = _valid_plays(_hand1)
    if not plays:
        return
    best = max(
        plays,
        key=lambda t: (
            _simulate_score_after_play(t),
            _is_double(t),
            t[0] + t[1],
        ),
    )
    opts = _play_options(best[0], best[1]) if not _played_dominoes.is_empty() else []
    tgt = opts[0] if len(opts) <= 1 else _best_direction_for(best[0], best[1], opts)
    if _apply_play_to_hand(best[0], best[1], _hand1, target_end=tgt):
        _set_message(f"Computer played [{best[0]}|{best[1]}].")
        _after_play(1, best)
    else:
        _set_message("Computer could not play - passing.")
        _start_turn(0)


# ---------------------------------------------------------------------------
# Text board dump (printed to stdout after every play)
# ---------------------------------------------------------------------------


def _make_sparse_row(positions: dict[int, str], width: int) -> str:
    """Return a string of length ``width`` with characters at specified columns."""
    row = [" "] * width
    for col, ch in positions.items():
        if 0 <= col < width:
            row[col] = ch
    return "".join(row).rstrip()


def _branch_section_lines(
    doubles_with_col: list[tuple[PlayedDomino, int]],
    direction: str,
    run_w: int,
) -> list[str]:
    """Return text rows for all branch bones in ``direction`` (up or down).

    Each bone contributes three rows: top pip, ``-`` divider, bottom pip.
    For ``"up"`` branches the farthest bone (deepest index) is emitted first
    so the result reads top-to-bottom correctly.
    """
    # Cache chains once to avoid repeated linked-list traversal.
    chains: list[tuple[int, list[PlayedDomino]]] = [
        (col, _get_branch_chain(b, direction)) for b, col in doubles_with_col
    ]
    max_depth = max((len(ch) for _, ch in chains), default=0)
    if max_depth == 0:
        return []
    depth_range = range(max_depth - 1, -1, -1) if direction == "up" else range(max_depth)
    lines: list[str] = []
    for depth in depth_range:
        top_pips: dict[int, str] = {}
        divs: dict[int, str] = {}
        bot_pips: dict[int, str] = {}
        for col, chain in chains:
            if depth < len(chain):
                bone = chain[depth]
                top_pips[col] = str(bone.value[0])
                divs[col] = "-"
                bot_pips[col] = str(bone.value[1])
        lines.extend(
            [
                _make_sparse_row(top_pips, run_w),
                _make_sparse_row(divs, run_w),
                _make_sparse_row(bot_pips, run_w),
            ]
        )
    return lines


def _board_text_lines() -> list[str]:
    """Return the board as a list of text lines.

    Each non-double in the horizontal run is rendered as ``[a,b]`` (5 chars).
    Each double is rendered as ``+`` (1 char) and its pip value is shown on
    the rows immediately above and below the run.  Vertical branch bones are
    shown beneath (or above) those pip rows, three lines per bone (top pip,
    ``-`` divider, bottom pip).
    """
    if _played_dominoes.is_empty():
        return ["(empty board)"]
    run = _played_dominoes.horizontal_run()

    # Compute char-column offset for each bone in the run.
    offsets: list[int] = []
    cur_x = 0
    for b in run:
        offsets.append(cur_x)
        cur_x += 1 if b.is_double else 5
    run_w = max(cur_x, 1)

    doubles_with_col: list[tuple[PlayedDomino, int]] = [
        (b, offsets[i]) for i, b in enumerate(run) if b.is_double
    ]

    pip_row = _make_sparse_row({col: str(b.value[0]) for b, col in doubles_with_col}, run_w)
    run_line = "".join("+" if b.is_double else f"[{b.value[0]},{b.value[1]}]" for b in run)

    lines: list[str] = _branch_section_lines(doubles_with_col, "up", run_w)
    if doubles_with_col:
        lines.append(pip_row)
    lines.append(run_line)
    if doubles_with_col:
        lines.append(pip_row)
    lines.extend(_branch_section_lines(doubles_with_col, "down", run_w))
    return lines


def _print_board_state(player_idx: int, bone_played: list[int]) -> None:
    """Print the board state to stdout after a bone is played."""
    hand = _hand0 if player_idx == 0 else _hand1
    player_name = "Human" if player_idx == 0 else "Computer"
    print(f"{player_name} played {bone_played}, hand: {len(hand)} {hand}")
    print("=" * 32)
    for line in _board_text_lines():
        print(line)
    print("=" * 32)
    pips = _played_dominoes.playable_pips()
    pip_text = "(any)" if pips is None else str(sorted(pips))
    print(f"Playable: {pip_text}, Value: {_played_dominoes.score()}")


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _draw_panel(
    screen: pygame.Surface,
    rect: pygame.Rect,
    *,
    highlight: bool = False,
) -> None:
    """Draw a filled rounded panel with a thin border."""
    bg = DRAW_MODE_BG if highlight else (0, 0, 0)
    border = DRAW_MODE_BORDER if highlight else (80, 80, 80)
    pygame.draw.rect(screen, bg, rect, border_radius=6)
    pygame.draw.rect(screen, border, rect, 2, border_radius=6)


def _blit_label(
    screen: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    x: int,
    y: int,
    color: tuple[int, int, int] = TEXT_COLOR,
) -> None:
    """Render text and blit it at (x, y)."""
    screen.blit(font.render(text, True, color), (x, y))


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------


def _render_header(screen: pygame.Surface, font: pygame.font.Font, rect: pygame.Rect) -> None:
    """Render the title bar."""
    _blit_label(screen, font, "Claussoft Dominoes - Racehorse", rect.x + 8, rect.y + 8, GOLD_COLOR)


def _render_cpu_hand(screen: pygame.Surface, font: pygame.font.Font, rect: pygame.Rect) -> None:
    """Render the computer's face-down hand at the top."""
    _draw_panel(screen, rect)
    count_txt = f"Computer's hand ({len(_hand1)} bones)"
    lbl = font.render(count_txt, True, TEXT_COLOR)
    screen.blit(lbl, (rect.centerx - lbl.get_width() // 2, rect.y + 4))
    if not _hand1:
        return
    bw = BONE_W
    surf_w = bw + 6  # portrait width
    surf_h = 2 * bw + 10  # portrait height
    total_w = len(_hand1) * surf_w + (len(_hand1) - 1) * _BONE_GAP_PX
    bx = rect.x + (rect.width - total_w) // 2
    by = rect.y + (rect.height - surf_h) // 2 + 8
    for _ in _hand1:
        surf = _make_facedown_surface(bw, horizontal=False, skin=_active_facedown)
        screen.blit(surf, (bx, by))
        bx += surf_w + _BONE_GAP_PX


def _render_boneyard(
    screen: pygame.Surface,
    font: pygame.font.Font,
    rect: pygame.Rect,
    targets: list[tuple[pygame.Rect, str, dict[str, object]]],
) -> None:
    """Render the boneyard panel."""
    _draw_panel(screen, rect, highlight=_needs_boneyard_draw)
    lbl_txt = f"Boneyard ({len(_boneyard)})"
    lbl = font.render(lbl_txt, True, TEXT_COLOR)
    screen.blit(lbl, (rect.centerx - lbl.get_width() // 2, rect.y + 4))
    if not _boneyard:
        _blit_label(screen, font, "(empty)", rect.x + 6, rect.y + 22)
        return
    bw = BONE_W - 8
    surf_w = 2 * bw + 10
    surf_h = bw + 6
    y = rect.y + 22
    for i, _ in enumerate(_boneyard):
        if y + surf_h > rect.bottom - 4:
            remaining = len(_boneyard) - i
            _blit_label(screen, font, f"+ {remaining} more...", rect.x + 6, y)
            break
        bx = rect.x + (rect.width - surf_w) // 2
        surf = _make_facedown_surface(bw, horizontal=True, skin=_active_facedown)
        screen.blit(surf, (bx, y))
        if _needs_boneyard_draw and not _game_over:
            targets.append((pygame.Rect(bx, y, surf_w, surf_h), "draw_boneyard", {}))
        y += surf_h + 2
    if _needs_boneyard_draw:
        lbl = font.render("Click to draw", True, GOLD_COLOR)
        screen.blit(lbl, (rect.x + (rect.width - lbl.get_width()) // 2, rect.bottom - 20))


def _compute_run_layout(run: list[PlayedDomino], w: int) -> list[tuple[PlayedDomino, int, bool]]:
    """Compute (bone, x_offset_from_run_start, is_landscape) for each run bone.

    Doubles are always rendered portrait (perpendicular to the run) so they
    visually appear rotated 90 degrees from the surrounding landscape bones.

    Args:
        run: the horizontal run of PlayedDomino objects.
        w: bone half-size in pixels.
    """
    pad, div = 3, 4
    portrait_w = w + 2 * pad
    landscape_w = 2 * w + div + 2 * pad
    layout: list[tuple[PlayedDomino, int, bool]] = []
    cur_x = 0
    for b in run:
        is_landscape = not b.is_double  # doubles are always portrait (perpendicular)
        bw = landscape_w if is_landscape else portrait_w
        layout.append((b, cur_x, is_landscape))
        cur_x += bw + _BONE_GAP_PX
    return layout


def _collect_bone_renders(
    run_layout: list[tuple[PlayedDomino, int, bool]],
    w: int,
    start_x: int,
    center_y: int,
) -> list[tuple[PlayedDomino, int, int, bool]]:
    """Return a flat list of (bone, screen_x, screen_y, is_landscape) for rendering.

    Includes both run bones and their branch bones.

    Args:
        run_layout: output of _compute_run_layout.
        w: bone half-size in pixels.
        start_x: x coordinate of the run's leftmost bone.
        center_y: y coordinate of the horizontal chain's vertical centre.
    """
    pad, div = 3, 4
    portrait_h = 2 * w + div + 2 * pad
    landscape_h = w + 2 * pad
    renders: list[tuple[PlayedDomino, int, int, bool]] = []
    for b, x_off, is_landscape in run_layout:
        bh = landscape_h if is_landscape else portrait_h
        bx = start_x + x_off
        by = center_y - bh // 2
        renders.append((b, bx, by, is_landscape))
        if not is_landscape:
            up_chain = _get_branch_chain(b, "up")
            down_chain = _get_branch_chain(b, "down")
            branch_y = by - _BONE_GAP_PX
            for ub in reversed(up_chain):
                branch_y -= portrait_h
                renders.append((ub, bx, branch_y, False))
                branch_y -= _BONE_GAP_PX
            branch_y = by + portrait_h + _BONE_GAP_PX
            for db in down_chain:
                renders.append((db, bx, branch_y, False))
                branch_y += portrait_h + _BONE_GAP_PX
    return renders


def _drop_indicator_rect(bone_rect: pygame.Rect, direction: str) -> pygame.Rect:
    """Compute the screen rect for a drop-zone indicator next to a bone."""
    ind = 22
    if direction == "left":
        return pygame.Rect(bone_rect.left - ind - 4, bone_rect.centery - ind // 2, ind, ind)
    if direction == "right":
        return pygame.Rect(bone_rect.right + 4, bone_rect.centery - ind // 2, ind, ind)
    if direction == "up":
        return pygame.Rect(bone_rect.centerx - ind // 2, bone_rect.top - ind - 4, ind, ind)
    return pygame.Rect(bone_rect.centerx - ind // 2, bone_rect.bottom + 4, ind, ind)


def _render_play_area(
    screen: pygame.Surface,
    font: pygame.font.Font,
    rect: pygame.Rect,
    targets: list[tuple[pygame.Rect, str, dict[str, object]]],
) -> None:
    """Render the play area including the domino chain and drop-zone indicators."""
    pygame.draw.rect(screen, (20, 60, 20), rect, border_radius=6)
    pygame.draw.rect(screen, (150, 180, 150), rect, 2, border_radius=6)
    if _played_dominoes.is_empty():
        has_sel = _selected_bone is not None and _current_player == 0 and not _game_over
        hint = "Click a bone in your hand, then click here to play" if has_sel else "Play area"
        color = DROP_ZONE_COLOR if has_sel else (150, 150, 150)
        _blit_label(screen, font, hint, rect.x + 8, rect.centery - 8, color)
        if has_sel:
            targets.append((rect, "play_first", {}))
        return

    w = _compute_bone_size(rect.width, rect.height)
    pad, div = 3, 4
    portrait_h = 2 * w + div + 2 * pad
    run = _played_dominoes.horizontal_run()
    run_layout = _compute_run_layout(run, w)

    # Total run width
    if run_layout:
        _, last_x, last_land = run_layout[-1]
        last_bw = (2 * w + div + 2 * pad) if last_land else (w + 2 * pad)
        total_run_w = last_x + last_bw
    else:
        total_run_w = 0

    # Vertical centering: account for branches
    max_up = max(
        (len(_get_branch_chain(b, "up")) for b, _, land in run_layout if not land),
        default=0,
    )
    max_down = max(
        (len(_get_branch_chain(b, "down")) for b, _, land in run_layout if not land),
        default=0,
    )
    branch_cell_h = portrait_h + _BONE_GAP_PX
    start_x = rect.x + max(0, (rect.width - total_run_w) // 2)
    center_y = rect.y + rect.height // 2
    center_y = max(center_y, rect.y + max_up * branch_cell_h + portrait_h // 2 + 8)
    center_y = min(center_y, rect.bottom - max_down * branch_cell_h - portrait_h // 2 - 8)

    bone_renders = _collect_bone_renders(run_layout, w, start_x, center_y)

    # Draw all bones inside the clipped play area
    bone_rects: dict[int, pygame.Rect] = {}
    screen.set_clip(rect)
    for b, bx, by, is_landscape in bone_renders:
        surf = _make_domino_surface(b.value[0], b.value[1], w, horizontal=is_landscape)
        screen.blit(surf, (bx, by))
        bone_rects[id(b)] = pygame.Rect(bx, by, surf.get_width(), surf.get_height())

    # Draw drop-zone indicators for the selected bone
    if _selected_bone is not None and _current_player == 0 and not _game_over:
        top_v, bot_v = _selected_bone[0], _selected_bone[1]
        for target_bone, direction in _played_dominoes.play_options(top_v, bot_v):
            if id(target_bone) not in bone_rects:
                continue
            ind_rect = _drop_indicator_rect(bone_rects[id(target_bone)], direction)
            if not rect.colliderect(ind_rect):
                continue
            pygame.draw.rect(screen, DROP_ZONE_COLOR, ind_rect, border_radius=4)
            lbl = font.render(direction[0].upper(), True, (0, 0, 0))
            screen.blit(lbl, lbl.get_rect(center=ind_rect.center))
            targets.append((ind_rect, "play_end", {"target_bone": target_bone, "direction": direction}))

    screen.set_clip(None)


def _render_scoreboard(screen: pygame.Surface, font: pygame.font.Font, rect: pygame.Rect) -> None:
    """Render the score panel."""
    _draw_panel(screen, rect)
    cx = rect.centerx
    score_lbl = font.render("Score", True, GOLD_COLOR)
    screen.blit(score_lbl, score_lbl.get_rect(centerx=cx, top=rect.y + 4))
    y = rect.y + 26
    for label, idx in (("You", 0), ("CPU", 1)):
        _blit_label(screen, font, f"{label}: {_scores[idx]}", rect.x + 8, y)
        y += 18
    y += 4
    pips = _played_dominoes.playable_pips()
    pip_text = "Open: (any)" if pips is None else f"Open: {tuple(sorted(pips))}"
    _blit_label(screen, font, pip_text, rect.x + 4, y)
    y += 16
    _blit_label(screen, font, f"Board: {_played_dominoes.score()}", rect.x + 4, y)
    if _game_over:
        y += 20
        _blit_label(screen, font, "[New Game button below]", rect.x + 4, y)


def _render_player_hand(
    screen: pygame.Surface,
    font: pygame.font.Font,
    rect: pygame.Rect,
    targets: list[tuple[pygame.Rect, str, dict[str, object]]],
) -> None:
    """Render the human player's hand."""
    _draw_panel(screen, rect)
    hand_lbl_txt = "Your hand  (click a bone, then click an arrow in the play area)"
    hand_lbl = font.render(hand_lbl_txt, True, TEXT_COLOR)
    screen.blit(hand_lbl, (rect.centerx - hand_lbl.get_width() // 2, rect.y + 2))
    if not _hand0:
        _blit_label(screen, font, "(empty)", rect.x + 8, rect.y + 22)
        return
    bw = BONE_W
    surf_w = bw + 6
    surf_h = 2 * bw + 10
    total_w = len(_hand0) * surf_w + (len(_hand0) - 1) * _BONE_GAP_PX
    bx = rect.x + max(4, (rect.width - total_w) // 2)
    by = rect.y + (rect.height - surf_h) // 2 + 8
    is_human_turn = _current_player == 0 and not _game_over and not _needs_boneyard_draw
    for bone in _hand0:
        is_sel = _selected_bone is not None and _bones_match(_selected_bone, bone[0], bone[1])
        surf = _make_domino_surface(bone[0], bone[1], bw, selected=is_sel)
        screen.blit(surf, (bx, by))
        if is_human_turn:
            targets.append((pygame.Rect(bx, by, surf_w, surf_h), "select_hand", {"bone": bone}))
        bx += surf_w + _BONE_GAP_PX


def _render_status(screen: pygame.Surface, font: pygame.font.Font, rect: pygame.Rect) -> None:
    """Render the scrollable message history."""
    _draw_panel(screen, rect)
    line_h = font.get_linesize()
    max_lines = max(1, (rect.height - 8) // line_h)
    messages = _messages[-max_lines:]
    y = rect.bottom - 4 - line_h * len(messages)
    for msg in messages:
        _blit_label(screen, font, msg, rect.x + 6, y)
        y += line_h


def _render_new_game_overlay(
    screen: pygame.Surface,
    font: pygame.font.Font,
    targets: list[tuple[pygame.Rect, str, dict[str, object]]],
) -> None:
    """Overlay a New Game button when the match is over."""
    if not _game_over:
        return
    sw, sh = screen.get_size()
    btn_w, btn_h = 160, 44
    btn_rect = pygame.Rect(sw // 2 - btn_w // 2, sh // 2 - btn_h // 2, btn_w, btn_h)
    pygame.draw.rect(screen, GOLD_COLOR, btn_rect, border_radius=8)
    lbl = font.render("New Game", True, (0, 0, 0))
    screen.blit(lbl, lbl.get_rect(center=btn_rect.center))
    targets.append((btn_rect, "new_game", {}))


def _render_all(screen: pygame.Surface, font_sm: pygame.font.Font, font_lg: pygame.font.Font) -> None:
    """Render the complete game state and rebuild the click-target list."""
    global _click_targets
    targets: list[tuple[pygame.Rect, str, dict[str, object]]] = []
    screen.fill(BG_COLOR)
    sw, sh = screen.get_size()

    header_rect = pygame.Rect(0, 0, sw, HEADER_H)
    cpu_rect = pygame.Rect(0, HEADER_H, sw, CPU_HAND_H)
    mid_y = HEADER_H + CPU_HAND_H + GAP
    mid_h = sh - mid_y - PLAYER_HAND_H - STATUS_H - 3 * GAP
    boneyard_rect = pygame.Rect(GAP, mid_y, BONEYARD_W, mid_h)
    play_rect = pygame.Rect(
        BONEYARD_W + 2 * GAP,
        mid_y,
        sw - BONEYARD_W - SCORE_W - 4 * GAP,
        mid_h,
    )
    score_rect = pygame.Rect(sw - SCORE_W - GAP, mid_y, SCORE_W, mid_h)
    hand_rect = pygame.Rect(0, mid_y + mid_h + GAP, sw, PLAYER_HAND_H)
    status_rect = pygame.Rect(0, sh - STATUS_H, sw, STATUS_H)

    _render_header(screen, font_lg, header_rect)
    _render_cpu_hand(screen, font_sm, cpu_rect)
    _render_boneyard(screen, font_sm, boneyard_rect, targets)
    _render_play_area(screen, font_sm, play_rect, targets)
    _render_scoreboard(screen, font_sm, score_rect)
    _render_player_hand(screen, font_sm, hand_rect, targets)
    _render_status(screen, font_sm, status_rect)
    _render_new_game_overlay(screen, font_lg, targets)

    _click_targets = targets


# ---------------------------------------------------------------------------
# Event / click handling
# ---------------------------------------------------------------------------


def _handle_play_first() -> None:
    """Place the selected bone as the first play on an empty board."""
    global _selected_bone
    if _selected_bone is None or _current_player != 0 or _game_over:
        return
    top, bottom = _selected_bone[0], _selected_bone[1]
    if _apply_play_to_hand(top, bottom, _hand0):
        played = list(_selected_bone)
        _selected_bone = None
        _after_play(0, played)
    else:
        _set_message("Could not play that bone.")


def _handle_play_end(target_bone: PlayedDomino, direction: str) -> None:
    """Place the selected bone at a specific end of the play area."""
    global _selected_bone
    if _selected_bone is None or _current_player != 0 or _game_over:
        return
    top, bottom = _selected_bone[0], _selected_bone[1]
    nb = _played_dominoes.apply_play(top, bottom, target_bone=target_bone, target_direction=direction)
    if nb:
        bone = _find_bone(_hand0, top, bottom)
        if bone is not None:
            _hand0.remove(bone)
        played = list(_selected_bone)
        _selected_bone = None
        _after_play(0, played)
    else:
        _set_message(f"[{top}|{bottom}] does not fit on the {direction} end.")


def _handle_boneyard_draw() -> None:
    """Draw a random bone from the boneyard into the player's hand."""
    global _needs_boneyard_draw, _consecutive_passes
    if not _needs_boneyard_draw or _game_over or not _boneyard:
        return
    bone = _boneyard.pop(random.randrange(len(_boneyard)))
    _hand0.append(bone)
    if _valid_plays(_hand0) or len(_boneyard) <= _BONEYARD_MIN:
        _needs_boneyard_draw = False
        if _valid_plays(_hand0):
            _set_message("Drew a bone from the boneyard. Your turn: click a domino to play.")
        else:
            _consecutive_passes += 1
            if _consecutive_passes >= 2:
                _end_stuck_game()
            else:
                _set_message("Drew a bone but still no playable bones. Computer's turn.")
                _start_turn(1)
    else:
        _set_message("Drew a bone. Still no playable bones - draw another.")


def _dispatch_click_action(action: str, data: dict[str, object]) -> None:
    """Execute the game action associated with a clicked target."""
    global _selected_bone
    if action == "select_hand":
        bone = data["bone"]
        if not isinstance(bone, list):
            return
        if _selected_bone is not None and _bones_match(_selected_bone, bone[0], bone[1]):
            _selected_bone = None  # deselect on second click
        else:
            _selected_bone = bone
            if not _can_play(bone[0], bone[1]) and not _played_dominoes.is_empty():
                _set_message(f"[{bone[0]}|{bone[1]}] has no valid play right now.")
                _selected_bone = None
    elif action == "play_first":
        _handle_play_first()
    elif action == "play_end":
        tb = data.get("target_bone")
        d = data.get("direction")
        if isinstance(tb, PlayedDomino) and isinstance(d, str):
            _handle_play_end(tb, d)
    elif action == "draw_boneyard":
        _handle_boneyard_draw()
    elif action == "new_game":
        _new_game()


def _handle_mouse_click(pos: tuple[int, int]) -> None:
    """Dispatch a left-button click to the appropriate game action."""
    for rect, action, data in _click_targets:
        if not rect.collidepoint(pos):
            continue
        _dispatch_click_action(action, data)
        break


# ---------------------------------------------------------------------------
# New game
# ---------------------------------------------------------------------------


def _new_game() -> None:
    """Initialise a fresh game, resetting all mutable state."""
    global _hand0, _hand1, _boneyard
    global _current_player, _needs_boneyard_draw, _game_over
    global _consecutive_passes, _game_num, _scores, _selected_bone, _messages
    state = deal_game()
    _hand0 = [list(b) for b in state.player0_hand]
    _hand1 = [list(b) for b in state.player1_hand]
    _boneyard = [list(b) for b in state.boneyard]
    _played_dominoes.clear()
    _scores = [0, 0]
    _current_player = 0
    _needs_boneyard_draw = False
    _game_over = False
    _consecutive_passes = 0
    _game_num = 0
    _selected_bone = None
    _messages = []
    pygame.time.set_timer(_COMPUTER_PLAY_EVENT, 0)  # cancel any pending timer
    _set_message("Your turn: click a domino from your hand.")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Open a PyGame-CE window and run the Racehorse Dominoes game."""
    global _facedown_surfaces, _active_facedown
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H), pygame.RESIZABLE)
    pygame.display.set_caption("Claussoft Dominoes - Racehorse")
    clock = pygame.time.Clock()
    font_sm = pygame.font.SysFont("sans-serif", 14)
    font_lg = pygame.font.SysFont("sans-serif", 20)

    _facedown_surfaces = _load_facedown_surfaces(BONE_W)
    _active_facedown = next(iter(_facedown_surfaces.values()), None)

    _new_game()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                _handle_mouse_click(event.pos)
            elif event.type == _COMPUTER_PLAY_EVENT:
                if _computer_must_draw:
                    _computer_draw_and_play()
                else:
                    _computer_play()
        _render_all(screen, font_sm, font_lg)
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()
