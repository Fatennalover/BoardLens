import chess
import pytest
from zipfile import ZipFile

from chess_helper.app import MainWindow
from chess_helper.openings import load_openings, opening_name, played_moves


def test_settings_workspace_fills_width_and_compact_reuses_controls(qt):
    window = MainWindow()
    window.resize(1400, 900)
    window.show()
    settings = window.settings_tabs
    try:
        window.open_settings()
        window.seconds.setValue(2.5)
        window.multi.layout_cards()
        qt.processEvents()
        assert window.workspace_stack.currentWidget() is window.settings_page
        assert settings.width() > 1250
        assert not window.workspace_toolbar.isVisible() and not window.analysis_options_bar.isVisible()
        window.toggle_compact(True)
        window.resize(530, 850)
        qt.processEvents()
        toolbar = window.workspace_toolbar
        for button in (window.suggest_button, window.live_button, window.quick_scan_button):
            assert button.isVisible() and toolbar.rect().contains(button.geometry())
        assert window.quick_scan_button.y() > window.suggest_button.y()
        options = (window.only_my_color, window.stick_to_move, window.steady_arrows, window.quick_arrows)
        bar = window.analysis_options_bar
        assert bar.isVisible()
        for button in options:
            assert button.isVisible() and button.isCheckable() and button.parentWidget() is bar
            assert bar.rect().contains(button.geometry()) and button.width() >= button.sizeHint().width()
        assert len({button.y() for button in options}) == 1
        window.open_settings()
        assert settings.isVisible() and window.seconds.value() == 2.5
    finally:
        window.close()


def test_moves_and_opening_follow_position_and_layout(qt):
    window = MainWindow()
    try:
        window.load_opening_index()
        board = window.tracker.board
        for move in ("e4", "e5", "Nf3", "Nc6", "Bb5"):
            board.push_san(move)
        window.refresh_board()
        window.analysis_tabs.setCurrentIndex(1)
        assert "Ruy Lopez" in window.moves_opening.text()
        assert window.moves_log.toPlainText() == "1. e4    e5\n2. Nf3    Nc6\n3. Bb5"
        window.undo()
        assert "Bb5" not in window.moves_log.toPlainText()
    finally:
        window.close()


def test_opening_matches_even_without_move_stack():
    position = chess.Board()
    for move in ("e4", "c5"):
        position.push_san(move)
    index = load_openings()
    assert "Sicilian Defense" in opening_name(chess.Board(position.fen()), index)
    assert not played_moves(chess.Board(position.fen()))


def test_autoplay_recovers_after_previous_analysis_had_no_result(qt, monkeypatch):
    monkeypatch.setenv("BOARDLENS_AUTOPLAY_LAB", "1")
    window = MainWindow()
    try:
        window.last_requested_fen = window.tracker.board.fen()
        requests = []
        monkeypatch.setattr(window, "suggest", lambda **kw: requests.append(kw))
        window.autoplay_test.start()
        assert requests == [{"from_poll": True}]
    finally:
        window.close()


def test_autoplay_stays_armed_when_leaving_and_returning_to_board(qt, monkeypatch):
    from types import SimpleNamespace

    window = MainWindow()
    player = window.autoplay_test
    offers = []
    reader = SimpleNamespace(offer_autoplay=lambda read,move: offers.append(move.uci()),
                             clear_autoplay=lambda source: None)
    fen = window.tracker.board.fen()
    read = SimpleNamespace(source_id='bot-tab', practice_id='selected-bot', practice_white=True,
                           practice_focused=False, play_protocol=2, exact_fen=fen,
                           received_at=float('inf'))
    try:
        monkeypatch.setattr(window, 'stop', lambda: None)
        monkeypatch.setattr(window, 'start_live', lambda **kwargs: None)
        window.source.setCurrentIndex(1)
        window.browser_reader = reader
        window._monitoring = window._turn_known = True
        window._last_read = read
        window.result = {'fen':fen, 'lines':[{'move':'e2e4'}]}
        monkeypatch.setattr(window, 'displayed_result', lambda result: result)
        player.delay.setValue(0)
        player.start()
        assert player.active and not offers

        window._screen_confirmed = True
        read.practice_focused = True
        window._reviewing = True
        player.tick()
        assert player.active and not offers
        window._reviewing = False
        read.source_id = 'different-tab'
        player.tick()
        assert player.active and not offers
        read.source_id = 'bot-tab'
        player.tick()
        assert player.active and offers == ['e2e4']
        player.stop()
        assert not player.active
    finally:
        window.browser_reader = None
        window.close()


@pytest.mark.parametrize('next_identity', ['round-one', 'round-two'])
def test_autoplay_rearms_for_new_bot_game_in_same_tab(qt, monkeypatch, next_identity):
    from types import SimpleNamespace

    window = MainWindow()
    player = window.autoplay_test
    offers = []
    reader = SimpleNamespace(offer_autoplay=lambda read, move: offers.append((read.practice_id, move.uci())),
                             clear_autoplay=lambda source: None)
    try:
        monkeypatch.setattr(window, 'start_live', lambda **kwargs: None)
        window.source.setCurrentIndex(1)
        window.browser_reader = reader
        window._monitoring = window._turn_known = window._screen_confirmed = True
        fen = window.tracker.board.fen()
        read = SimpleNamespace(source_id='bot-tab', practice_id='round-one', game_identity='round-one',
                               practice_kind='computer-bot', practice_white=True, practice_focused=True,
                               play_protocol=2, exact_fen=fen, received_at=float('inf'))
        window._last_read = read
        monkeypatch.setattr(window, 'displayed_result', lambda result: result)
        player.delay.setValue(0)
        window.result = {'fen':fen, 'lines':[{'move':'e2e4'}]}
        player.start()
        assert offers == [('round-one','e2e4')]

        read.practice_id = None
        read.game_result = 'Game over'
        window.visible_game_end(fen, 'Game over')
        player.tick()
        assert player.active and player.finished_fen == fen

        read.game_result = None
        read.practice_id = read.game_identity = next_identity
        window.game_ended = False
        window.result = {'fen':fen, 'lines':[{'move':'d2d4'}]}
        read.source_id = 'unrelated-tab'
        player.tick()
        assert len(offers) == 1
        read.source_id = 'bot-tab'
        player.tick()
        assert player.active and offers[-1] == (next_identity,'d2d4')

        player.stop()
        read.practice_id = 'round-three'
        player.tick()
        assert not player.active and len(offers) == 2
    finally:
        player.stop()
        window.browser_reader = None
        window.close()


def test_browser_setup_exports_a_standalone_zip(qt, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog, QLabel
    from chess_helper.browser_setup import BrowserSetup

    target = tmp_path / 'BoardLens-BrowserReader.zip'
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *_: (str(target), 'ZIP'))
    window = MainWindow()
    setup = BrowserSetup(window)
    try:
        setup.download_extension()
        with ZipFile(target) as archive:
            assert archive.testzip() is None
            assert 'BrowserReader/manifest.json' in archive.namelist()
            assert all(name.startswith('BrowserReader/') for name in archive.namelist())
        assert 'ZIP saved' in setup.feedback.text()
        assert all('/Users/' not in label.text() for label in setup.findChildren(QLabel))
    finally:
        setup.close()
        window.close()
