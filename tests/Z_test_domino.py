from math import pi

from Pythonista.domino import Domino


def test_domino_rotate_90() -> None:
    domino = Domino()
    assert domino.rotation == 0
    domino.rotate_90()
    assert domino.rotation == pi / 2
    domino.rotate_90()
    assert domino.rotation == pi
    domino.rotate_90()
    assert domino.rotation == 3 * pi / 2
    domino.rotate_90()
    assert domino.rotation == 0


def test_domino_rotate_180() -> None:
    domino = Domino()
    assert domino.rotation == 0
    domino.rotate_180()
    assert domino.rotation == pi
    domino.rotate_180()
    assert domino.rotation == 0


def test_domino_reset() -> None:
    domino = Domino()
    domino.rotate_90()
    assert domino.rotation == pi / 2
    domino.reset()
    assert domino.rotation == 0
    domino.rotate_180()
    assert domino.rotation == pi
    domino.reset()
    assert domino.rotation == 0


def test_domino_horizontal() -> None:
    domino = Domino()
    assert domino.horizontal
    domino.rotate_90()
    assert not domino.horizontal
    domino.rotate_90()
    assert domino.horizontal
    domino.rotate_180()
    assert domino.horizontal
    domino.rotate_180()
    assert domino.horizontal
    domino.rotate_90()
    assert not domino.horizontal
    domino.rotate_90()
    assert domino.horizontal
