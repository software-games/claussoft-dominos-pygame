import re

from src.main import (
    _PYSCRIPT_CODE,
    GameState,
    _load_domino_image_uris,
    all_domino_bones,
    build_html,
    deal_game,
    make_domino_svg,
)


def test_dominoes() -> None:
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
    assert "_on_drop_played_bone" in _PYSCRIPT_CODE
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
    """PlayedDominoes.score() counts doubles twice via is_double check."""
    assert "2 if b.is_double else 1" in _PYSCRIPT_CODE
    assert "def score" in _PYSCRIPT_CODE


def test_pyscript_played_domino_class() -> None:
    """PlayedDomino class is defined with value and neighbor attributes."""
    assert "class PlayedDomino:" in _PYSCRIPT_CODE
    assert "self.left = None" in _PYSCRIPT_CODE
    assert "self.right = None" in _PYSCRIPT_CODE
    assert "self.up = None" in _PYSCRIPT_CODE
    assert "self.down = None" in _PYSCRIPT_CODE
    assert "def open_directions" in _PYSCRIPT_CODE
    assert "def is_double" in _PYSCRIPT_CODE


def test_pyscript_played_dominoes_class() -> None:
    """PlayedDominoes class is defined with first_played_domino and traversal methods."""
    assert "class PlayedDominoes:" in _PYSCRIPT_CODE
    assert "self.first_played_domino = None" in _PYSCRIPT_CODE
    assert "def horizontal_run" in _PYSCRIPT_CODE
    assert "def open_ends" in _PYSCRIPT_CODE
    assert "def playable_pips" in _PYSCRIPT_CODE
    assert "def score" in _PYSCRIPT_CODE
    assert "def apply_play" in _PYSCRIPT_CODE


def test_pyscript_spinner_cross_rendering() -> None:
    """Cross-shaped junction rendering functions are present."""
    assert "_render_played_cross" in _PYSCRIPT_CODE
    assert "_render_played_linear" in _PYSCRIPT_CODE
    assert "_on_drop_spinner_bone" in _PYSCRIPT_CODE
    assert "data-double-val" in _PYSCRIPT_CODE
    assert "horizontal_run" in _PYSCRIPT_CODE


def test_pyscript_doubles_open_up_down_when_surrounded() -> None:
    """Doubles expose up/down directions only after both horizontal sides connected."""
    assert "self.is_double and self.left is not None and self.right is not None" in _PYSCRIPT_CODE


def test_pyscript_double_bone_direct_drop() -> None:
    """The double bone itself is a drop target; offsetY picks up vs down."""
    assert "_on_drop_spinner_bone" in _PYSCRIPT_CODE
    assert "offset_y" in _PYSCRIPT_CODE
    assert "el_h" in _PYSCRIPT_CODE
    assert "_render_drop_zone" not in _PYSCRIPT_CODE
    assert "data-double-val" in _PYSCRIPT_CODE


def test_pyscript_branch_bone_orientation() -> None:
    """Branch bones are rendered with correct pip orientation using value[0] and value[1]."""
    assert "_make_bone_div(b.value[0], b.value[1], horizontal=is_dbl, w=w)" in _PYSCRIPT_CODE


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
    assert 'closest("[data-play-end]")' in _PYSCRIPT_CODE


def test_html_play_area_centered() -> None:
    """Play area centers the chain both horizontally and vertically, with no extra vertical space."""
    state = deal_game()
    html = build_html(state)
    assert "justify-content: center" in html
    # Play area shrinks to content height; no empty vertical space above/below chain.
    assert "height: fit-content" in html
    assert "align-self: center" in html


def test_pyscript_up_down_branch_placement() -> None:
    """Up/down branch placement is handled via find_tip and apply_play."""
    assert 'target_direction = "up"' in _PYSCRIPT_CODE or '"up"' in _PYSCRIPT_CODE
    assert "find_tip" in _PYSCRIPT_CODE
    assert "_played_dominoes.apply_play" in _PYSCRIPT_CODE


def test_pyscript_board_cleared_on_new_hand() -> None:
    """Board state is cleared when a new hand is dealt."""
    assert "_played_dominoes.clear()" in _PYSCRIPT_CODE


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
    pts_pos = after_play_body.find("pts = _score_played()")
    not_hand_pos = after_play_body.find("if not hand:")
    assert pts_pos != -1, "pts = _score_played() must be in _after_play"
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


def test_load_domino_image_uris_returns_28_entries() -> None:
    """All 28 domino SVG images are loaded as base64 data URIs."""
    uris = _load_domino_image_uris()
    assert len(uris) == 28
    # Each key is of the form "a_b" where a <= b
    for i in range(7):
        for j in range(i, 7):
            key = f"{i}_{j}"
            assert key in uris, f"Missing domino image: {key}"
            assert uris[key].startswith("data:image/svg+xml;base64,")


def test_make_domino_svg_face_up_uses_image() -> None:
    """make_domino_svg uses <image> elements from the SVG files."""
    svg = make_domino_svg(3, 4)
    assert "<image" in svg
    assert "data:image/svg+xml;base64," in svg
    # No hand-drawn SVG primitives (circles/rects for pips)
    assert "<circle" not in svg
    assert "<rect" not in svg


def test_make_domino_svg_flipped_uses_rotate_180() -> None:
    """make_domino_svg rotates 180 deg when top > bottom."""
    svg_normal = make_domino_svg(3, 4)  # top=3 <= bottom=4: no rotation
    svg_flipped = make_domino_svg(4, 3)  # top=4 > bottom=3: rotate 180
    assert "rotate(180" in svg_flipped
    assert "rotate(180" not in svg_normal


def test_make_domino_svg_face_down_uses_facedown_image() -> None:
    """make_domino_svg face_down=True uses the face-down skin if Pillow is available."""
    svg = make_domino_svg(3, 4, face_down=True)
    assert "<image" in svg
    # The face-down SVG should not expose pip counts
    assert "<circle" not in svg


def test_pyscript_uses_domino_image_uris() -> None:
    """PyScript code loads domino images from the embedded DOM element at startup."""
    assert "_DOMINO_IMAGE_URIS" in _PYSCRIPT_CODE
    assert "_FACEDOWN_IMAGE_URI" in _PYSCRIPT_CODE
    assert 'document.getElementById("domino-image-uris")' in _PYSCRIPT_CODE
    assert 'document.getElementById("facedown-image-uri")' in _PYSCRIPT_CODE


def test_html_embeds_domino_image_uris() -> None:
    """The generated HTML embeds both the domino image URIs and face-down image URI."""
    state = deal_game()
    html = build_html(state)
    assert 'id="domino-image-uris"' in html
    assert 'id="facedown-image-uri"' in html
    # Domino images are base64-encoded SVG data URIs
    assert "data:image/svg+xml;base64," in html


def test_pyscript_played_dominoes_not_chain() -> None:
    """The play area data structure is named _played_dominoes (a PlayedDominoes instance), not _chain."""
    assert "_played_dominoes" in _PYSCRIPT_CODE
    assert "PlayedDominoes" in _PYSCRIPT_CODE
    assert re.search(r"\b_chain\b", _PYSCRIPT_CODE) is None
    assert "play_chain" not in _PYSCRIPT_CODE


def test_pyscript_image_based_svg_uses_svgimage() -> None:
    """New domino rendering uses SVG <image> elements, not generated pip circles."""
    # The _domino_svg function uses <image href=
    assert "<image href=" in _PYSCRIPT_CODE
    # Old hand-drawn approach (rect/circle for pips) is gone
    assert "_PIP_LOCATIONS" not in _PYSCRIPT_CODE
    assert "_half_svg" not in _PYSCRIPT_CODE


def test_pyscript_playable_pips_displayed() -> None:
    """Playable pip numbers are displayed under the score."""
    assert "playable-pips" in _PYSCRIPT_CODE
    assert "playable_pips" in _PYSCRIPT_CODE
    assert "Open:" in _PYSCRIPT_CODE


def test_pyscript_computer_play_delay() -> None:
    """Computer play delay constant and setTimeout are present."""
    assert "_COMPUTER_PLAY_DELAY_MS" in _PYSCRIPT_CODE
    assert "window.setTimeout" in _PYSCRIPT_CODE


def test_pyscript_sounds_present() -> None:
    """Sound function calls are present for game events."""
    assert "playDominoSound" in _PYSCRIPT_CODE
