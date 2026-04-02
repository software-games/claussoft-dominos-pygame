# Claussoft Dominoes from Claussoft International
[__Racehorse dominoes__](http://www.dominorules.com/racehorse)

Rules:
* Each player is initially dealt a hand of 7 dominoes
* The remaining dominoes go face down in the boneyard
* Dominoes can only be played against matching numbers
* If no domino in a player's hand matches an outside domino then the player must take a domino from the boneyard until a domino can play or until the boneyard only has two dominoes left
* If all outside dominoes add up to a multiple of 5 then the player gets points (sum // 5) and goes again
* If the player plays doubles, they get to go again.  Note: Doubles are played sideways and when exposed count 2x.
* The player who has no dominoes gets all points on the other player's dominoes // 5
* First player to 30 points wins the match

## Running the game

```
uv run src/main.py
```

This opens a **PyGame-CE** window.  Dominoes are drawn programmatically.
Click a bone in your hand to select it (gold border), then click one of the
green arrow indicators that appear in the play area to place it.  When you
have no playable bones the boneyard panel is highlighted — click any
face-down bone there to draw.

Requires Python ≥ 3.13.  Dependencies are declared via [PEP 723](https://peps.python.org/pep-0723/) inline metadata and installed automatically by `uv run`.

## Running the tests

```
pytest
```

The test suite covers game-state serialization, the board data structures
(`PlayedDomino` / `PlayedDominoes`), scoring logic, and the bone-size
height-constraint formula.
