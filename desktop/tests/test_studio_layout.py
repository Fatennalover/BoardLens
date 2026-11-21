import chess
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
            assert 'BrowserReader/coach.js' in archive.namelist()
            assert all(name.startswith('BrowserReader/') for name in archive.namelist())
        assert 'ZIP saved' in setup.feedback.text()
        assert all('/Users/' not in label.text() for label in setup.findChildren(QLabel))
    finally:
        setup.close()
        window.close()
