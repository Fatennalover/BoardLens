import json
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import chess
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

from chess_helper.app import MainWindow
from chess_helper.direct_boards import BrowserReader, exact_read
from chess_helper.core import load_settings
from chess_helper.coach_engine import CoachSettings
from chess_helper.engine import EngineJob, summarize
from chess_helper.overlay import COACH_PREVIEW_COLOR


def test_desktop_coach_follows_current_position_and_suggestions(qt, monkeypatch):
    window = MainWindow()
    coach_search = window.coach_search
    calls = []

    def coach_text():
        return "\n".join(label.text() for label in window.coach.findChildren(QLabel) if label.isVisible())

    def wait_for_results():
        deadline = time.monotonic() + 2
        while not coach_search.result and time.monotonic() < deadline:
            qt.processEvents()
            time.sleep(.005)
        assert coach_search.result

    run = EngineJob.run
    def search(job, engine, board, settings):
        if job.session is not coach_search.session:
            return run(job, engine, board, settings)
        calls.append(settings)
        moves = ("e2e4", "d2d4", "c2c4") if board.turn else ("e7e5", "c7c5")
        reply = "e7e5" if board.turn else "g1f3"
        return summarize(board, [
            {"pv": [chess.Move.from_uci(move), chess.Move.from_uci(reply)],
             "score": chess.engine.PovScore(chess.engine.Cp(20), chess.WHITE)}
            for move in moves[:settings.multipv]
        ], "Coach test engine")

    try:
        monkeypatch.setattr(EngineJob, "run", search)
        from chess_helper import engine_config
        original_command = engine_config.command
        monkeypatch.setattr(engine_config, "command", lambda owner, index=None:
                            "test-stockfish" if index == 0 else original_command(owner, index))
        window.recommendation_preset(1)
        coach_search.preferences.update(multipv=2, seconds=.7, depth=13, mode="Time + depth")
        window.resize(920, 720)
        window.show()
        window.analysis_tabs.setCurrentWidget(window.coach)
        qt.processEvents()
        assert window.coach.suggest_button.isVisible()
        assert "See what you could play next" in coach_text()
        tabs = window.analysis_tabs.tabBar()
        assert all(tabs.rect().contains(tabs.tabRect(i)) for i in range(tabs.count()))

        board = window.tracker.board
        result = summarize(board, [
            {"pv": [chess.Move.from_uci("h2h4")],
             "score": chess.engine.PovScore(chess.engine.Cp(-60), chess.WHITE)}
        ], "Primary test engine")
        window.result = result
        window.render_result(result)
        assert "Primary test engine" not in coach_text()
        window.coach.suggest_button.click()
        wait_for_results()
        text = coach_text()
        assert not window.coach.suggest_button.isVisible()
        assert "+0.20 for White" in text
        assert "Coach test engine" in text
        assert "Occupies a central square" in text
        assert text.count("Likely reply") == 2 and "c4" not in text
        assert (calls[0].engine_id, calls[0].seconds, calls[0].depth, calls[0].multipv) == ("stockfish", .7, 13, 2)
        assert window.result["engine"] == "Primary test engine" and window.multipv.value() == 1

        def previews():
            return [arrow["move"].uci() for arrow in window.board_view.arrows if arrow.get("preview") and not arrow.get("reply")]

        first, second = window.coach._cards
        qt.processEvents()
        assert first.height() >= first.layout().minimumSize().height()
        QTest.mouseClick(first, Qt.MouseButton.LeftButton)
        assert previews() == ["e2e4"] and first.isChecked()
        assert any(a.get("preview") and a.get("dashed") and a["move"].uci() == "e7e5"
                   for a in window.board_view.arrows)
        assert window.tracker.board.fen() == chess.STARTING_FEN
        QTest.keyClick(second, Qt.Key.Key_Space)
        assert previews() == ["d2d4"] and second.isChecked() and not first.isChecked()
        QTest.mouseClick(second, Qt.MouseButton.LeftButton)
        assert not previews() and not second.isChecked()

        window.orientation.setCurrentIndex(2)  # Changing orientation stops the current app searches.
        window.coach.suggest_button.click()
        wait_for_results()
        assert "-0.20 for Black" in coach_text()

        window._white_bottom = chess.BLACK
        window.only_my_color.setChecked(True)
        assert "Waiting for your side to move" in coach_text()
        assert "Likely reply" not in coach_text()
        assert not window.coach.suggest_button.isVisible()

        board = board.copy()
        board.push_san("e4")
        window.set_position(board)
        assert "Black to move" in coach_text()
        assert "Coach test engine" not in coach_text()
        window.coach.suggest_button.click()
        wait_for_results()
        QTest.mouseClick(window.coach._cards[0], Qt.MouseButton.LeftButton)
        assert previews() == ["e7e5"]
        window.practice_click(chess.E7)
        window.practice_click(chess.E5)
        assert window.tracker.board.turn == chess.WHITE
        assert not previews()
        window.save(quiet=True)
        assert load_settings()["coach"]["seconds"] == .7
        assert load_settings()["seconds"] == window.seconds.value()

        window.toggle_compact(True)
        window.analysis_tabs.setCurrentIndex(0)
        window.show_coach()
        assert window.coach.isVisible()
    finally:
        window.close()


def test_coach_settings_expose_only_supported_limits(qt):
    window = MainWindow()
    try:
        dialog = CoachSettings(window, window.coach_search.preferences)
        assert dialog.engine.currentData() == "stockfish"
        assert dialog.preferences()["strength"] == "Full strength"
        dialog.fields["mode"].setCurrentText("Depth")
        assert not dialog.form.isRowVisible(dialog.fields["seconds"])
        assert dialog.form.isRowVisible(dialog.fields["depth"])
        dialog.fields["prediction_plies"].setValue(1)
        assert not dialog.form.isRowVisible(dialog.fields["prediction_seconds"])
        dialog.engine.setCurrentIndex(dialog.engine.findData("custom"))
        assert dialog.form.isRowVisible(dialog.custom_row)
        assert dialog.preferences()["engine_id"] == "custom"
        dialog.close()
    finally:
        window.close()


def test_browser_coach_keeps_current_moves_and_can_run_without_overlays(qt, monkeypatch):
    window = MainWindow()
    monkeypatch.setattr(window, 'start_live', lambda **_: None)
    window.source.setCurrentIndex(1)
    reader = BrowserReader(port=0)
    window.browser_reader = reader
    try:
        board = window.tracker.board
        window.recommendation_preset(5)
        candidates = ['e2e4', 'd2d4', 'c2c4', 'g1f3', 'b1c3']
        result = summarize(board, [
            {'pv': [chess.Move.from_uci(move), chess.Move.from_uci('e7e5')],
             'score': chess.engine.PovScore(chess.engine.Cp(20), chess.WHITE)}
            for move in candidates
        ], 'Coach test engine')
        window.result = result
        identity = 'browser:qa:0'
        window._last_read = exact_read(board.fen(), chess.WHITE, identity)
        window._screen_confirmed = True
        window._monitoring = True
        assert window.quick_arrows.text() == 'Screen arrows'
        window.quick_arrows.click()
        window.browser_eval_enabled.setChecked(False)
        window.result = result
        window.publish_reader_hints()
        hint = reader.hints[identity]
        assert hint['arrows'] == [] and hint['evaluation'] is None
        assert window.board_view.arrows
        assert [move['san'] for move in hint['coach']['moves']] == ['e4', 'd4', 'c4', 'Nf3', 'Nc3']
        assert hint['coach']['moves'][0]['reply_simple']
        assert hint['coach']['engine'] == 'Coach test engine'

        window.quick_arrows.click()
        window.publish_reader_hints()
        assert reader.hints[identity]['arrows']
        assert reader.hints[identity]['arrows'][0]['move'] == 'e2e4'

        monkeypatch.setattr(window.coach_search, "request", lambda board: None)
        window.coach_search.follow = True
        window.coach_search.result = result
        window.show_board_surface()
        window.analysis_tabs.setCurrentWidget(window.coach)
        window.coach._cards[0].click()
        window.publish_reader_hints()
        assert [a['move'] for a in reader.hints[identity]['arrows'] if a['color'] == COACH_PREVIEW_COLOR] == ["e2e4"]

        board.push_san('d4')
        window._last_read = exact_read(board.fen(), chess.WHITE, identity)
        window.refresh_board()
        window.publish_reader_hints()
        assert reader.hints[identity]['coach']['side'] == 'Black'
        assert reader.hints[identity]['coach']['moves'] == []
        assert not any(a['color'] == COACH_PREVIEW_COLOR for a in reader.hints[identity]['arrows'])
    finally:
        window.close()


def test_retired_browser_move_endpoint_rejects_even_a_paired_reader():
    reader = BrowserReader(port=0)
    try:
        url = f'http://127.0.0.1:{reader.port}/claim-play'
        request = Request(url, data=json.dumps({'move': 'e2e4'}).encode(),
                          headers={'Authorization': 'Bearer ' + reader.token})
        with pytest.raises(HTTPError) as error:
            urlopen(request, timeout=2)
        assert error.value.code == 404
    finally:
        reader.close()
