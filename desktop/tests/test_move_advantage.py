import chess
import pytest

from chess_helper.app import MainWindow
from chess_helper.move_advantage import comparison_rows
from test_app_engine import wait


@pytest.mark.parametrize("white,expected", [(True, ("+0.20", "-0.60")), (False, ("-0.20", "+0.60"))])
def test_move_changes_use_the_movers_perspective(white, expected):
    rows = comparison_rows({"cp": 40}, [{"san": "e4", "cp": 60}, {"san": "d4", "cp": -20}], white)
    assert tuple(row["change"] for row in rows) == expected


def test_mate_uses_mate_distance():
    rows = comparison_rows({"cp": -350}, [{"san": "Qh2#", "mate": -1}], False)
    assert rows == [{"move": "Qh2#", "score": "Mate in 1", "change": "Mate changes"}]


def test_comparison_runs_independently_and_follows_practice_moves(qt):
    window = MainWindow()
    try:
        if not window.engine_path.text():
            pytest.skip("Stockfish missing")
        window.source.setCurrentIndex(0)
        window.multipv.setValue(1)
        window.eval_seconds.setValue(.2)
        window.phone.apply_settings({"advantage_count": 3, "advantage_engine": 0})
        panel = window.move_advantage
        wait(qt, lambda: panel.result is not None)
        assert panel.result["side"] == "White"
        assert len(panel.result["rows"]) == 3
        assert window.phone.snapshot()["boards"][0]["move_advantage"] == panel.result
        assert window.multipv.value() == 1 and window.result is None

        window.tracker.board.push_san("e4")
        window.refresh_board()
        assert panel.result is None
        wait(qt, lambda: panel.result is not None)
        assert panel.result["side"] == "Black"
        assert panel.result["fen"] == window.tracker.board.fen()
        board = chess.Board(panel.result["fen"])
        assert all(board.parse_san(row["move"]) in board.legal_moves for row in panel.result["rows"])
        window.advantage_count.setValue(0)
        assert panel.result is None
    finally:
        window.close()
