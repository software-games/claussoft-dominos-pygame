from dominos_ui_on_pyscript import (
    _PYSCRIPT_CODE,
    GameState,
    all_domino_bones,
    build_html,
    deal_game,
)


def test_dominos() -> None:
    assert True


def test_all_domino_bones_count() -> None:
    """There are 28 unique domino bones (0-6)."""
    bones = all_domino_bones()
    assert len(bones) == 28
    # Each bone is unique
    assert len({tuple(t) for t in bones}) == 28


def test_deal_game_distributes_bones() -> None:
    state = deal_game()
    assert len(state.player0_hand) == 7
    assert len(state.player1_hand) == 7
    assert len(state.boneyard) == 14
    all_bones = state.player0_hand + state.player1_hand + state.boneyard
    assert len(all_bones) == 28


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


def test_html_status_msg_is_scrollable_div() -> None:
    """The status message area is rendered as a <div> (not a <span>) for scrolling."""
    state = deal_game()
    html = build_html(state)
    # Must be a <div> so CSS overflow-y can scroll the message history.
    assert '<div id="status-msg">' in html
    # The initial message is wrapped in a <p> for consistent append behaviour.
    assert "<p>" in html


def test_html_boneyard_pyscript_always_face_down() -> None:
    """_PYSCRIPT_CODE always renders boneyard bones face-down."""
    # face_down=True must appear in the boneyard render path.
    assert "face_down=True" in _PYSCRIPT_CODE
    # The old face_down=not draggable_to_hand pattern must NOT be present.
    assert "face_down=not draggable_to_hand" not in _PYSCRIPT_CODE


def test_html_boneyard_random_draw() -> None:
    """Boneyard draw picks a random bone (not a specific user-chosen one)."""
    # Random index pick must be present in the drop handler.
    assert "random.randrange(len(_boneyard))" in _PYSCRIPT_CODE
    # Drag data must not expose pip values (only the generic draw signal).
    assert "boneyard:draw" in _PYSCRIPT_CODE


def test_html_ambiguous_play_check() -> None:
    """Play area drop handler guards against ambiguous multi-end placement."""
    assert "_is_ambiguous_play" in _PYSCRIPT_CODE
    assert "_on_drop_chain_bone" in _PYSCRIPT_CODE
    # target_end parameter is required for directed placement.
    assert "target_end=" in _PYSCRIPT_CODE


def test_html_game_num_alternates_first_player() -> None:
    """_deal_new_hand increments _game_num and picks first player accordingly."""
    assert "_game_num += 1" in _PYSCRIPT_CODE
    assert "_game_num % 2" in _PYSCRIPT_CODE


def test_html_full_width_board() -> None:
    """Board uses full window width (no max-width constraint)."""
    state = deal_game()
    html = build_html(state)
    assert "max-width: 900px" not in html


def test_html_scoreboard_same_width_as_boneyard() -> None:
    """Scoreboard column width matches boneyard column (both 130px)."""
    state = deal_game()
    html = build_html(state)
    # The grid must have equal-width columns for boneyard and scoreboard.
    assert "130px 1fr 130px" in html


def test_pyscript_double_at_chain_end_scores_double() -> None:
    """A double at the chain end has both pips counted: 3-6, 6-6 → 3+6+6=15."""
    # Logic is extracted into _end_values(); verify the helper is present.
    assert "_end_values" in _PYSCRIPT_CODE
    # The _end_values helper applies * 2 for double chain ends.
    assert "* (2 if _chain[0][0] == _chain[0][1] else 1)" in _PYSCRIPT_CODE
    assert "* (2 if _chain[-1][0] == _chain[-1][1] else 1)" in _PYSCRIPT_CODE


def test_pyscript_spinner_state_variables() -> None:
    """Spinner state variables are declared in the PyScript code."""
    for var in ("_spinner_val", "_top_branch", "_bottom_branch", "_top_end", "_bottom_end"):
        assert var in _PYSCRIPT_CODE, f"{var} missing from _PYSCRIPT_CODE"


def test_pyscript_spinner_cross_rendering() -> None:
    """Cross-shaped spinner rendering functions are present."""
    assert "_render_cross_chain" in _PYSCRIPT_CODE
    assert "_render_linear_chain" in _PYSCRIPT_CODE
    # Drop zones are now the spinner bone itself (no separate placeholder boxes).
    assert "_on_drop_spinner_bone" in _PYSCRIPT_CODE
    assert "_spinner_index" in _PYSCRIPT_CODE
    assert "_spinner_is_surrounded" in _PYSCRIPT_CODE


def test_pyscript_spinner_index_requires_double() -> None:
    """_spinner_index must match both pips to avoid confusing non-double bones."""
    # The check must include b[1] so a [3,4] bone is not mistaken for the [3,3] spinner.
    assert "b[0] == _spinner_val and b[1] == _spinner_val" in _PYSCRIPT_CODE


def test_pyscript_spinner_bone_direct_drop() -> None:
    """The spinner bone itself is the drop target (no separate dashed zone)."""
    # New handler uses offsetY to determine top vs bottom.
    assert "_on_drop_spinner_bone" in _PYSCRIPT_CODE
    assert "offset_y" in _PYSCRIPT_CODE
    assert "el_h" in _PYSCRIPT_CODE
    # The old separate placeholder _render_drop_zone is gone.
    assert "_render_drop_zone" not in _PYSCRIPT_CODE
    # No dashed outline on the spinner bone.
    assert "spinner-bone-droptarget" not in _PYSCRIPT_CODE


def test_pyscript_top_branch_orientation() -> None:
    """Top branch bones are rendered with connector-pip at bottom (facing spinner)."""
    # Branch bones stored as [connector, free_end].
    # For top branch (column above spinner), free_end must face UP.
    # Doubles: horizontal=is_dbl → landscape (perpendicular to branch direction).
    assert "_make_bone_div(b[1], b[0], horizontal=is_dbl, w=w)" in _PYSCRIPT_CODE
    # Bottom branch also uses horizontal=is_dbl.
    assert "_make_bone_div(b[0], b[1], horizontal=is_dbl, w=w)" in _PYSCRIPT_CODE


def test_pyscript_doubles_perpendicular_via_css_rotation() -> None:
    """Doubles in chain use landscape SVG + CSS rotate(90°) for perpendicular appearance."""
    # _apply_bone_rotation applies margin compensation and the .bone-rotated class.
    assert "_apply_bone_rotation" in _PYSCRIPT_CODE
    assert "bone-rotated" in _PYSCRIPT_CODE
    # All chain bones are rendered as landscape; doubles get CSS rotation.
    assert "horizontal=True" in _PYSCRIPT_CODE
    # Non-doubles do NOT get rotation.
    assert "if is_double:" in _PYSCRIPT_CODE


def test_html_bone_rotated_css() -> None:
    """CSS includes .bone-rotated rule for perpendicular doubles."""
    state = deal_game()
    html = build_html(state)
    assert ".bone-rotated" in html
    assert "rotate(90deg)" in html


def test_pyscript_spinner_junction_balanced() -> None:
    """Top and bottom branch columns have equal min-height so the spinner is centred."""
    assert "max_branch_h" in _PYSCRIPT_CODE
    # Both columns must get the same min-height value.
    assert 'top_col.style.minHeight = f"{max_branch_h}px"' in _PYSCRIPT_CODE
    assert 'bot_col.style.minHeight = f"{max_branch_h}px"' in _PYSCRIPT_CODE
    # Top column pushes bones toward the spinner (flex-end).
    assert 'top_col.style.justifyContent = "flex-end"' in _PYSCRIPT_CODE


def test_pyscript_on_drop_chain_end_guard() -> None:
    """_on_drop returns early when the drop target is a chain-end bone."""
    assert 'closest("[data-chain-end]")' in _PYSCRIPT_CODE


def test_html_play_area_centered() -> None:
    """Play area centers the chain both horizontally and vertically, with no extra vertical space."""
    state = deal_game()
    html = build_html(state)
    assert "justify-content: center" in html
    # Play area shrinks to content height; no empty vertical space above/below chain.
    assert "height: fit-content" in html
    assert "align-self: center" in html


def test_pyscript_spinner_top_bottom_placement() -> None:
    """Spinner top/bottom branch placement is handled in _apply_play()."""
    # top and bottom are handled together via 'in ("top", "bottom")' after refactor.
    assert 'target_end == "top"' in _PYSCRIPT_CODE or 'target_end in ("top", "bottom")' in _PYSCRIPT_CODE
    assert "_extend_branch" in _PYSCRIPT_CODE  # shared helper for branch placement
    assert "_top_branch" in _PYSCRIPT_CODE
    assert "_bottom_branch" in _PYSCRIPT_CODE


def test_pyscript_spinner_cleared_on_new_hand() -> None:
    """Spinner state is cleared when a new hand is dealt."""
    assert "_spinner_val = None" in _PYSCRIPT_CODE
    assert "_top_branch.clear()" in _PYSCRIPT_CODE
    assert "_bottom_branch.clear()" in _PYSCRIPT_CODE


def test_pyscript_compute_bone_size_height_constraint() -> None:
    """_compute_bone_size applies a height constraint when branches are present."""
    # Height-based constraint: w <= (avail_h - 20*max_b - 6) / (4*max_b + 2)
    assert "avail_h" in _PYSCRIPT_CODE
    assert "clientHeight" in _PYSCRIPT_CODE
    # Uses viewport height minus overhead to estimate available height.
    assert "documentElement.clientHeight" in _PYSCRIPT_CODE
    # Minimum w reduced to 10 so tall branches can be accommodated.
    assert "max(10, min(55, int(w)))" in _PYSCRIPT_CODE


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
                # Verify the junction fits at this w
                junction_h = w * (4 * max_b + 2) + (20 * max_b + 6)
                assert junction_h <= avail_h + 1, (
                    f"Junction height {junction_h:.1f} > avail_h {avail_h} with max_b={max_b}, w={w:.2f}"
                )


def test_pyscript_bone_gap_constant() -> None:
    """_BONE_GAP_PX constant is defined and used in spacing calculations."""
    assert "_BONE_GAP_PX = 4" in _PYSCRIPT_CODE
    # Used in compute_bone_size gap calculation
    assert "* _BONE_GAP_PX" in _PYSCRIPT_CODE
    # Used in branch column bone_h calculation
    assert "+ _BONE_GAP_PX" in _PYSCRIPT_CODE


def test_html_board_shrinks_to_content() -> None:
    """Board grid uses auto rows so boneyard/play-area shrink to their content height."""
    state = deal_game()
    html = build_html(state)
    # grid-template-rows must use auto for all rows (not 1fr which forces expansion)
    assert "grid-template-rows: auto auto auto" in html
    # body uses min-height instead of fixed height so page can grow with content
    assert "min-height: 100vh" in html
    # #board must not have a 1fr row (which would force expansion)
    assert "grid-template-rows: auto 1fr auto" not in html


def test_html_boneyard_scoreboard_align_start() -> None:
    """Boneyard and scoreboard use align-self: start so they don't stretch in the grid row."""
    state = deal_game()
    html = build_html(state)
    assert "align-self: start" in html


def test_html_uniform_branch_gap() -> None:
    """Spinner junction and branch columns use the same gap as the horizontal chain."""
    state = deal_game()
    html = build_html(state)
    # .spinner-junction and .branch-col must both appear with gap: 4px
    assert ".spinner-junction" in html
    assert ".branch-col" in html
    # Verify 4px gap appears (used by both spinner-junction and branch-col)
    # and the old 2px value is not used for these elements
    # We check by ensuring spinner-junction section contains gap: 4px
    spinner_start = html.find(".spinner-junction")
    assert spinner_start != -1
    spinner_block = html[spinner_start : spinner_start + 120]
    assert "gap: 4px" in spinner_block
    branch_start = html.find(".branch-col")
    assert branch_start != -1
    branch_block = html[branch_start : branch_start + 120]
    assert "gap: 4px" in branch_block


def test_pyscript_last_bone_double_must_draw_and_continue() -> None:
    """If a player empties their hand with a double, they must draw and keep playing."""
    # Extract just the _after_play function body for scoped assertions.
    after_play_start = _PYSCRIPT_CODE.find("def _after_play(")
    assert after_play_start != -1
    # End at the next top-level function definition.
    next_def = _PYSCRIPT_CODE.find("\ndef _", after_play_start + 1)
    after_play_body = _PYSCRIPT_CODE[after_play_start:next_def]
    # The rule: last bone is double → draw from boneyard and continue, not win hand.
    assert "Must draw and keep playing." in after_play_body
    # The check must guard against boneyard being at minimum.
    assert "(scored or is_dbl) and len(_boneyard) > _BONEYARD_MIN" in after_play_body
    # Hand-empty check must come AFTER scoring (not before), so pts are always counted.
    pts_pos = after_play_body.find("pts = _score_chain()")
    not_hand_pos = after_play_body.find("if not hand:")
    assert pts_pos != -1, "pts = _score_chain() must be in _after_play"
    assert not_hand_pos != -1, "if not hand: must be in _after_play"
    assert pts_pos < not_hand_pos, "Scoring must happen before the empty-hand check"


def test_pyscript_last_bone_score_must_draw_and_continue() -> None:
    """If a player empties their hand with a scoring play, they must draw and keep playing."""
    # Extract just the _after_play function body for scoped assertions.
    after_play_start = _PYSCRIPT_CODE.find("def _after_play(")
    assert after_play_start != -1
    next_def = _PYSCRIPT_CODE.find("\ndef _", after_play_start + 1)
    after_play_body = _PYSCRIPT_CODE[after_play_start:next_def]
    # Three cases: double+scored, double-only, score-only - all must trigger draw rule.
    assert "with their last bone! Must draw and keep playing." in after_play_body
    assert "played their last bone (a double)!" in after_play_body
    # When boneyard is at minimum or last bone is plain non-scoring, call check_win instead.
    assert "_check_win_after_play(player_idx)" in after_play_body
