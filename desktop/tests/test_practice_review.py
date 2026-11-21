from pathlib import Path

import chess
import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QFileDialog

from chess_helper.app import MainWindow
from chess_helper.core import find_engine
from test_app_engine import wait


def prepare_engine(window):
    if not find_engine():
        pytest.skip("Install Stockfish for integration tests")
    window.mode.setCurrentText("Time")
    window.seconds.setValue(.1)
    window.only_my_color.setChecked(False)
    window.overlay_enabled.setChecked(True)


def test_switching_to_practice_keeps_the_scanned_board_and_moves(qt, monkeypatch):
    window = MainWindow()
    try:
        monkeypatch.setattr(window, "start_live", lambda **_: None)
        window.source.setCurrentIndex(1)
        board = chess.Board()
        for notation in ("e4", "c5", "Nf3"):
            board.push_san(notation)
        window.set_position(board)
        window.live_button.setChecked(True)
        window.quick_source.setCurrentIndex(0)

        assert window.tracker.board.fen() == board.fen()
        assert window.tracker.board.move_stack == board.move_stack
        assert window.local_turn.currentText() == "Black"
        assert window.live_button.isChecked()
        window.analysis_tabs.setCurrentIndex(1)
        window.moves_log.anchorClicked.emit(QUrl("move:2"))
        assert window.game_review.moves.currentRow() == 2
        earlier = board.copy()
        earlier.pop()
        assert window.game_review.view.board.fen() == earlier.fen()
        assert window.tracker.board.fen() == board.fen()

        window.local_turn.setCurrentText("White")
        assert window.tracker.board.turn == chess.WHITE
        assert window.tracker.board.board_fen() == board.board_fen()
        assert window.tracker.board.move_stack == []
        assert window.live_button.isChecked()
        window.toggle_compact(True)
        window.resize(530, 720)
        window.show()
        qt.processEvents()
        assert window.board_stack.rect().contains(window.board_area.geometry())
        assert window.board_area.rect().contains(window.board_view.geometry())
    finally:
        window.close()


def test_a_screenshot_stays_editable_as_the_engine_follows_moves(qt, monkeypatch):
    window = MainWindow()
    try:
        prepare_engine(window)
        image = Path(__file__).parent / "fixtures/chesscom-italian-white.png"
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(image), ""))
        window.quick_source.setCurrentIndex(2)
        assert not window.editable_position
        assert window.board_stack.currentIndex() == 1
        window.empty_scan_button.click()
        assert window.editable_position
        assert window.board_stack.currentIndex() == 0
        original = window.tracker.board.copy()
        assert original.board_fen() == "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R"

        def fail_if_reread(*a, **k):
            pytest.fail("Analyzing an edited screenshot must use its current position")

        monkeypatch.setattr(window._recognizer, "read", fail_if_reread)
        window.local_turn.setCurrentText("Black")
        black_fen = window.tracker.board.fen()
        wait(qt, lambda: window.result and window.result["fen"] == black_fen
             and not window.result.get("provisional"))
        assert window.board_view.arrows
        assert all(window.tracker.board.piece_at(arrow["move"].from_square).color == chess.BLACK
                   for arrow in window.board_view.arrows if not arrow.get("reply"))

        window.board_view.square_clicked.emit(chess.G8)
        window.board_view.square_clicked.emit(chess.F6)
        played_fen = window.tracker.board.fen()
        wait(qt, lambda: window.result and window.result["fen"] == played_fen
             and not window.result.get("provisional"))
        assert window.tracker.board.peek() == chess.Move.from_uci("g8f6")
        assert window.local_turn.currentText() == "White"

        window.review_button.click()
        assert window.game_review.moves.count() == 2
        window.game_review.moves.setCurrentRow(0)
        assert window.game_review.view.board.fen() == black_fen
        window.quick_source.setCurrentIndex(0)
        assert window.tracker.board.fen() == played_fen
        window.quick_source.setCurrentIndex(2)
        assert window.tracker.board.fen() == original.fen()
    finally:
        window.close()


def test_review_analyzes_every_played_position_with_selected_engine(qt):
    window = MainWindow()
    try:
        prepare_engine(window)
        window.custom_engine.setText(find_engine())
        board = chess.Board()
        for notation in ("e4", "e5", "Bc4", "Nc6"):
            board.push_san(notation)
        window.set_position(board)
        window.review_button.click()
        review = window.game_review
        review.engine.setCurrentIndex(review.engine.findText("Custom UCI"))
        assert review.engine.currentData() == 2
        review.analyze.click()
        wait(qt, lambda: review.job is None)
        assert review.progress.text() == "Game analysis complete"
        assert list(review.played.results) == list(range(5))
        review.previous.click()
        assert review.moves.currentRow() == 3
        assert review.variation.text().startswith("Engine line")
        assert review.view.arrows
        assert window.tracker.board.fen() == board.fen()
    finally:
        window.close()


def test_playing_out_a_checkmate_leaves_the_practice_board_intact(qt):
    window = MainWindow()
    try:
        prepare_engine(window)
        board = chess.Board("6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1")
        window.set_position(board)
        window.review_button.click()
        review = window.game_review
        review.play_out.click()
        wait(qt, lambda: review.job is None)
        assert review.progress.text() == "White wins · checkmate"
        assert review.moves.item(1).text() == "1. Re8#"
        assert review.view.arrows[0]["move"] == chess.Move.from_uci("e1e8")
        review.next.click()
        assert review.view.board.is_checkmate()
        assert review.details.text() == "White wins · checkmate"
        assert window.tracker.board.fen() == board.fen()
    finally:
        window.close()
