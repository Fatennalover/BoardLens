import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYNPUT_BACKEND", "dummy")
os.environ.setdefault("BOARDLENS_TEST_MODE", "1")

import pytest


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("BOARDLENS_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture(scope="session")
def qt():
    # Imported after flags are set. Unhide plugins in the downloaded Mac venv.
    if os.name != "nt" and hasattr(os, "chflags"):
        import stat
        import PySide6
        plugins = Path(PySide6.__file__).parent / "Qt" / "plugins"
        for path in [plugins, *plugins.rglob("*")]:
            flags = path.stat().st_flags
            if flags & stat.UF_HIDDEN:
                os.chflags(path, flags & ~stat.UF_HIDDEN)
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def render_board(qt):
    def render(board, white_bottom=True):
        from chess_helper.capture import pixmap_bgr
        from chess_helper.widgets import BoardView
        class FixtureBoard(BoardView):
            # Keep recognition inputs independent of the app's display artwork.
            LIGHT_TILE = "#e9e4d5"
            DARK_TILE = "#77988a"

            def draw_piece(self, painter, symbol, rect):
                self.pieces[symbol].render(painter, rect)

        view = FixtureBoard()
        view.resize(544, 544)
        view.board = board
        view.white_bottom = white_bottom
        return pixmap_bgr(view.grab())[16:528, 16:528].copy()
    return render
