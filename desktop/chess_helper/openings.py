"""Opening display data, derived from lichess-org/chess-openings (CC0)."""
from functools import lru_cache
import gzip
from pathlib import Path

import chess

ASSET = Path(__file__).parent / "assets/openings.tsv.gz"


@lru_cache(maxsize=1)
def load_openings():
    with gzip.open(ASSET, "rt", encoding="utf-8") as source:
        return dict((key, f"{eco} · {name}") for key, eco, name in
                    (line.rstrip("\n").split("\t", 2) for line in source))


def opening_name(board, openings):
    # Named positions are all early-game positions. Keep the last matched
    # opening as the game continues, including common transpositions.
    if not openings:
        return ""
    current = board.copy(stack=True)
    while True:
        if current.fullmove_number <= 40:
            key = f"{current.board_fen()} {'w' if current.turn else 'b'} {current.castling_xfen()}"
            if key in openings:
                return openings[key]
        if not current.move_stack:
            return ""
        current.pop()


def played_moves(board, move_label=None):
    position = board.root()
    rows = []
    for index, move in enumerate(board.move_stack, 1):
        number = position.fullmove_number
        san = position.san(move)
        if move_label is not None:
            san = move_label(index, san)
        if position.turn:
            rows.append(f"{number}. {san}")
        elif rows:
            rows[-1] += f"    {san}"
        else:
            rows.append(f"{number}… {san}")
        position.push(move)
    return "\n".join(rows)
