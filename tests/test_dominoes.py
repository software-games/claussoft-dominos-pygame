import pytest

import src.main as _main_module
from src.main import (
    GameState,
    PlayedDomino,
    PlayedDominoes,
    _board_text_lines,
    _compute_bone_size,
    _get_branch_chain,
    _played_dominoes,
    all_domino_bones,
    deal_game,
)

# ---------------------------------------------------------------------------
# Basic bone / deal tests
# ---------------------------------------------------------------------------


def test_dominoes() -> None:
    assert True


def test_all_domino_bones_count() -> None:
    """There are 28 unique domino bones (0-6)."""
    bones = all_domino_bones()
    assert len(bones) == 28
    assert len({tuple(t) for t in bones}) == 28


def test_deal_game_distributes_bones() -> None:
    state = deal_game()
    assert len(state.player0_hand) == 7
    assert len(state.player1_hand) == 7
    assert len(state.boneyard) == 14
    assert len(state.player0_hand + state.player1_hand + state.boneyard) == 28


def test_deal_game_no_duplicates() -> None:
    state = deal_game()
    all_bones = state.player0_hand + state.player1_hand + state.boneyard
    canonical = {(min(a, b), max(a, b)) for a, b in all_bones}
    assert len(canonical) == 28


def test_game_state_default_scores() -> None:
    state = deal_game()
    assert state.scores == [0, 0]
    assert state.current_player == 0


def test_game_state_serialization() -> None:
    state = deal_game()
    data = state.model_dump_json()
    restored = GameState.model_validate_json(data)
    assert restored.player0_hand == state.player0_hand
    assert restored.player1_hand == state.player1_hand
    assert restored.boneyard == state.boneyard
    assert restored.scores == [0, 0]


def test_game_state_game_num_default() -> None:
    """game_num starts at 0 (human plays first in the first hand)."""
    state = deal_game()
    assert state.game_num == 0


def test_game_state_game_num_serialization() -> None:
    """game_num survives a JSON round-trip."""
    state = GameState(
        player0_hand=[[0, 0]],
        player1_hand=[[0, 1]],
        boneyard=[[0, 2]],
        game_num=3,
    )
    restored = GameState.model_validate_json(state.model_dump_json())
    assert restored.game_num == 3


# ---------------------------------------------------------------------------
# PlayedDomino tests
# ---------------------------------------------------------------------------


def test_played_domino_is_double() -> None:
    assert PlayedDomino(4, 4).is_double is True
    assert PlayedDomino(3, 4).is_double is False


def test_played_domino_pip_at() -> None:
    b = PlayedDomino(3, 5)
    assert b.pip_at("left") == 3
    assert b.pip_at("up") == 3
    assert b.pip_at("right") == 5
    assert b.pip_at("down") == 5


def test_played_domino_pip_at_double() -> None:
    b = PlayedDomino(6, 6)
    for d in ("left", "right", "up", "down"):
        assert b.pip_at(d) == 6


def test_played_domino_open_directions_initial() -> None:
    b = PlayedDomino(3, 4)
    assert set(b.open_directions()) == {"left", "right"}


def test_played_domino_double_opens_up_down_after_horizontal_fill() -> None:
    b = PlayedDomino(6, 6)
    # Before both sides filled, no up/down.
    assert "up" not in b.open_directions()
    assert "down" not in b.open_directions()
    # Fill left side.
    b.left = PlayedDomino(0, 6)
    assert "up" not in b.open_directions()
    # Fill right side -> up and down become available.
    b.right = PlayedDomino(6, 1)
    assert "up" in b.open_directions()
    assert "down" in b.open_directions()


# ---------------------------------------------------------------------------
# PlayedDominoes tests
# ---------------------------------------------------------------------------


def test_played_dominoes_empty() -> None:
    pd = PlayedDominoes()
    assert pd.is_empty()
    assert pd.score() == 0
    assert pd.playable_pips() is None
    assert pd.horizontal_run() == []


def test_played_dominoes_first_play() -> None:
    pd = PlayedDominoes()
    pd.apply_play(3, 4)
    assert not pd.is_empty()
    assert pd.score() == 7


def test_played_dominoes_score_double_alone() -> None:
    """A lone double on an empty board scores value * 2."""
    pd = PlayedDominoes()
    pd.apply_play(6, 6)
    assert pd.score() == 12


def test_played_dominoes_apply_play_extends_chain() -> None:
    pd = PlayedDominoes()
    pd.apply_play(6, 6)
    # [6,6] has both sides open; must name the target direction.
    dbl = pd.horizontal_run()[0]
    pd.apply_play(6, 3, target_bone=dbl, target_direction="right")
    run = pd.horizontal_run()
    assert len(run) == 2


def test_played_dominoes_playable_pips() -> None:
    pd = PlayedDominoes()
    pd.apply_play(3, 4)
    pips = pd.playable_pips()
    assert pips is not None
    assert 3 in pips
    assert 4 in pips


def test_played_dominoes_can_play() -> None:
    pd = PlayedDominoes()
    assert pd.can_play(1, 2)  # empty board: any bone plays
    pd.apply_play(3, 4)
    assert pd.can_play(3, 1)
    assert pd.can_play(2, 4)
    assert not pd.can_play(1, 2)


def test_played_dominoes_clear() -> None:
    pd = PlayedDominoes()
    pd.apply_play(1, 1)
    pd.clear()
    assert pd.is_empty()


def test_played_dominoes_find_double_in_run() -> None:
    pd = PlayedDominoes()
    pd.apply_play(6, 6)
    pd.apply_play(6, 3)
    pd.apply_play(6, 1)
    dbl = pd.find_double_in_run(6)
    assert dbl is not None
    assert dbl.is_double


def test_played_dominoes_doubles_expose_up_down_when_surrounded() -> None:
    """Doubles expose up/down directions only after both horizontal sides are connected."""
    pd = PlayedDominoes()
    pd.apply_play(6, 6)
    run = pd.horizontal_run()
    dbl = run[0]
    assert "up" not in dbl.open_directions()
    # Place one bone on each side of the double.
    pd.apply_play(6, 3, target_bone=dbl, target_direction="right")
    pd.apply_play(6, 1, target_bone=dbl, target_direction="left")
    assert "up" in dbl.open_directions()
    assert "down" in dbl.open_directions()


# ---------------------------------------------------------------------------
# _get_branch_chain
# ---------------------------------------------------------------------------


def test_get_branch_chain_empty() -> None:
    b = PlayedDomino(6, 6)
    assert _get_branch_chain(b, "up") == []
    assert _get_branch_chain(b, "down") == []


def test_get_branch_chain_one_bone() -> None:
    spinner = PlayedDomino(6, 6)
    child = PlayedDomino(6, 3)
    spinner.up = child
    child.down = spinner
    chain = _get_branch_chain(spinner, "up")
    assert len(chain) == 1
    assert chain[0] is child


# ---------------------------------------------------------------------------
# _compute_bone_size (pure-maths formula check — no display needed)
# ---------------------------------------------------------------------------


def test_compute_bone_size_height_formula() -> None:
    """The height-constraint formula is analytically correct."""
    # Formula: junction_height = 2 * max_b * (2w+10) + (2w+6)
    #        = w*(4*max_b+2) + (20*max_b+6)
    # Solving for w: w = (avail_h - 20*max_b - 6) / (4*max_b + 2)
    for max_b in (1, 3, 5, 8):
        for avail_h in (200, 400, 600):
            denom = 4 * max_b + 2
            num = avail_h - 20 * max_b - 6
            if num > 0:
                w = num / denom
                junction_h = w * (4 * max_b + 2) + (20 * max_b + 6)
                assert junction_h <= avail_h + 1, (
                    f"Junction height {junction_h:.1f} > avail_h {avail_h} with max_b={max_b}, w={w:.2f}"
                )


def test_compute_bone_size_empty_board(monkeypatch: pytest.MonkeyPatch) -> None:
    """Returns BONE_W for an empty board."""
    monkeypatch.setattr(_main_module, "_played_dominoes", PlayedDominoes())
    result = _compute_bone_size(800, 400)
    assert result == _main_module.BONE_W


# ---------------------------------------------------------------------------
# Parametrized play-area scoring tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def board_classes() -> dict:
    """Provide PlayedDomino and PlayedDominoes for parametrized scoring tests."""
    return {"PlayedDomino": PlayedDomino, "PlayedDominoes": PlayedDominoes}


@pytest.mark.parametrize(
    ("dominoes", "scores"),
    [
        ([], (0,)),
        (["6_6"], (0, 12)),
        (["6_6", "6_3"], (0, 12, 15)),
        (["6_6", "6_3", "6_2"], (0, 12, 15, 5)),
    ],
)
def test_play_area_score_sequence(
    dominoes: list[str], scores: tuple[int, ...], board_classes: dict
) -> None:
    """PlayedDominoes.score() is correct after each bone is added to the play area."""
    PlayedDoms = board_classes["PlayedDominoes"]  # noqa: N806
    pd = PlayedDoms()
    assert pd.score() == scores[0], f"Empty board score should be {scores[0]}"
    for i, dom in enumerate(dominoes):
        a, b = map(int, dom.split("_"))
        if pd.is_empty():
            pd.apply_play(a, b)
        else:
            opts = pd.play_options(a, b)
            assert opts, f"No valid play for [{a}|{b}] at step {i + 1}"
            if len(opts) == 1:
                pd.apply_play(a, b)
            else:
                tb, td = opts[0]
                pd.apply_play(a, b, target_bone=tb, target_direction=td)
        assert pd.score() == scores[i + 1], (
            f"After playing {dom} (step {i + 1}), expected score {scores[i + 1]}"
        )


# ---------------------------------------------------------------------------
# open_directions - vertical branch bones
# ---------------------------------------------------------------------------


def test_open_directions_vertical_branch_up() -> None:
    """A bone placed in the up branch only exposes its 'up' open end."""
    spinner = PlayedDomino(4, 4)
    spinner.left = PlayedDomino(1, 4)
    spinner.right = PlayedDomino(4, 2)
    branch = PlayedDomino(4, 5)  # placed going up from spinner
    branch.down = spinner
    spinner.up = branch
    assert branch.open_directions() == ["up"]


def test_open_directions_vertical_branch_down() -> None:
    """A bone placed in the down branch only exposes its 'down' open end."""
    spinner = PlayedDomino(4, 4)
    spinner.left = PlayedDomino(1, 4)
    spinner.right = PlayedDomino(4, 2)
    branch = PlayedDomino(4, 3)  # placed going down from spinner
    branch.up = spinner
    spinner.down = branch
    assert branch.open_directions() == ["down"]


def test_open_directions_double_in_branch_no_sub_branches() -> None:
    """A double in the vertical branch does not expose left/right sub-branches."""
    spinner = PlayedDomino(3, 3)
    spinner.left = PlayedDomino(0, 3)
    spinner.right = PlayedDomino(3, 1)
    dbl_branch = PlayedDomino(3, 3)  # double in the down branch
    dbl_branch.up = spinner
    spinner.down = dbl_branch
    dirs = dbl_branch.open_directions()
    assert "left" not in dirs
    assert "right" not in dirs
    assert "down" in dirs


# ---------------------------------------------------------------------------
# score() - vertical branch tips
# ---------------------------------------------------------------------------


def test_score_with_branch_bone() -> None:
    """A branch tip bone is correctly included in the board score."""
    pd = PlayedDominoes()
    # Build: [1,4] -- [4,4] -- [4,2]  with [4,5] hanging below [4,4]
    pd.apply_play(4, 4)
    dbl = pd.horizontal_run()[0]
    pd.apply_play(1, 4, target_bone=dbl, target_direction="left")
    pd.apply_play(4, 2, target_bone=dbl, target_direction="right")
    # Now the spinner [4,4] has both sides filled; place a branch bone below it.
    pd.apply_play(4, 5, target_bone=dbl, target_direction="down")
    # Open ends: [1,4] left pip=1, [4,2] right pip=2, branch [?,5] down pip=5.
    # Score = 1 + 2 + 5 = 8.
    assert pd.score() == 8


def test_score_branch_double_counts_twice() -> None:
    """A double at the tip of a branch counts 2x its pip value."""
    pd = PlayedDominoes()
    pd.apply_play(3, 3)
    dbl = pd.horizontal_run()[0]
    pd.apply_play(0, 3, target_bone=dbl, target_direction="left")
    pd.apply_play(3, 1, target_bone=dbl, target_direction="right")
    # Place [3,3] double in the down branch.
    pd.apply_play(3, 3, target_bone=dbl, target_direction="down")
    # Open ends: left pip=0, right pip=1, branch double pip=3 (counts twice).
    # Score = 0 + 1 + 3*2 = 7.
    assert pd.score() == 7


def test_score_empty_spinner_branches_not_counted() -> None:
    """Empty vertical branches on a junction double are excluded from the score."""
    pd = PlayedDominoes()
    pd.apply_play(5, 5)
    dbl = pd.horizontal_run()[0]
    pd.apply_play(0, 5, target_bone=dbl, target_direction="left")
    pd.apply_play(5, 1, target_bone=dbl, target_direction="right")
    # Spinner is now a junction; up/down are open but empty - should not score.
    # Open ends: left=0, right=1; spinner's empty branches skipped.
    # Score = 0 + 1 = 1.
    assert pd.score() == 1


# ---------------------------------------------------------------------------
# _board_text_lines
# ---------------------------------------------------------------------------


def test_board_text_lines_empty() -> None:
    _played_dominoes.clear()
    lines = _board_text_lines()
    assert lines == ["(empty board)"]


def test_board_text_lines_single_non_double(monkeypatch: pytest.MonkeyPatch) -> None:
    pd = PlayedDominoes()
    pd.apply_play(3, 4)
    monkeypatch.setattr(_main_module, "_played_dominoes", pd)
    lines = _board_text_lines()
    assert any("[3,4]" in ln for ln in lines)


def test_board_text_lines_double_shown_as_plus(monkeypatch: pytest.MonkeyPatch) -> None:
    pd = PlayedDominoes()
    pd.apply_play(6, 6)
    monkeypatch.setattr(_main_module, "_played_dominoes", pd)
    lines = _board_text_lines()
    run_line = next(ln for ln in lines if "+" in ln or "[" in ln)
    assert "+" in run_line
    assert "[6,6]" not in run_line


def test_board_text_lines_branch_bone_shown(monkeypatch: pytest.MonkeyPatch) -> None:
    pd = PlayedDominoes()
    pd.apply_play(4, 4)
    dbl = pd.horizontal_run()[0]
    pd.apply_play(1, 4, target_bone=dbl, target_direction="left")
    pd.apply_play(4, 2, target_bone=dbl, target_direction="right")
    pd.apply_play(4, 5, target_bone=dbl, target_direction="down")
    monkeypatch.setattr(_main_module, "_played_dominoes", pd)
    lines = _board_text_lines()
    all_text = "\n".join(lines)
    # The branch bone value[1]=5 must appear somewhere below the run line.
    assert "5" in all_text
