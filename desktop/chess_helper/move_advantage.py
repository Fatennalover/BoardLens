"""Compare top moves with a separate, bounded engine search."""
from dataclasses import replace
from html import escape
from threading import Thread

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QSpinBox, QTextBrowser, QVBoxLayout, QWidget

from . import engine_config, engine_library
from .core import SearchSettings
from .engine import EngineJob, EngineSession


SCORERS = {"stockfish", "lc0", "gaia", "rodent", "custom"}
MAX_MOVES = 6


def score_text(line, sign):
    mate = line.get("mate")
    if mate is not None:
        return ("Mate in " if mate * sign > 0 else "Mated in ") + str(abs(mate))
    return f"{sign * line['cp'] / 100:+.2f}" if line.get("cp") is not None else "—"


def comparison_rows(baseline, candidates, white_to_move):
    sign = 1 if white_to_move else -1
    rows = []
    for line in candidates:
        if line.get("cp") is None and line.get("mate") is None:
            continue
        change = "—"
        if baseline.get("mate") is None and line.get("mate") is None:
            if baseline.get("cp") is not None:
                difference = sign * (line["cp"] - baseline["cp"])
                change = f"{difference / 100:+.2f}" if difference else "0.00"
        elif baseline.get("mate") != line.get("mate"):
            change = "Mate changes"
        rows.append({"move": line["san"], "score": score_text(line, sign), "change": change})
    return rows


class MoveAdvantage(QWidget):
    completed = Signal(int, object, str)

    def __init__(self, workspace):
        super().__init__()
        self.workspace = workspace
        self.session = EngineSession()
        self.generation = 0
        self.key = None
        self.result = self.job = None
        layout = QVBoxLayout(self)
        options = QFormLayout()
        options.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.engine = QComboBox()
        for index, item in enumerate(engine_library.ENTRIES):
            if item.kind in SCORERS:
                self.engine.addItem(item.label, index)
        self.count = QSpinBox()
        self.count.setRange(0, MAX_MOVES)
        self.count.setSpecialValueText("Off")
        self.count.setToolTip("Number of moves ranked by this engine, independent of Analysis candidates.")
        options.addRow("Scoring engine", self.engine)
        options.addRow("Moves to compare", self.count)
        layout.addLayout(options)
        hint = QLabel("Change from the current estimate, in pawns for the side to move.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.output = QTextBrowser()
        self.output.setAccessibleName("Move advantage results")
        layout.addWidget(self.output, 1)
        self.completed.connect(self.finish)
        self.count.valueChanged.connect(self.changed)
        self.engine.currentIndexChanged.connect(self.changed)
        self.output.setPlainText("Choose how many moves to compare.")

    def changed(self, *_):
        self.workspace.queue_autosave()
        self.refresh()

    def refresh(self):
        w = self.workspace
        count = self.count.value()
        board = w.tracker.board if w.editable_position or w._reviewing or w._screen_confirmed else None
        if not count or board is None or not board.is_valid() or board.is_game_over() or w.game_ended:
            self.clear()
            self.output.setPlainText("Choose how many moves to compare." if not count else "Waiting for a playable position.")
            return
        index = self.engine.currentData()
        key = (board.fen(), index, count, w.eval_seconds.value(), w.eval_depth.value(),
               w.engine_path.text(), w.custom_engine.text())
        if self.key == key:
            return
        self.clear()
        self.key = key
        entry = engine_library.ENTRIES[index]
        try:
            command = engine_config.command(w, index)
        except (ValueError, OSError) as error:
            self.output.setPlainText(str(error))
            return
        limits = SearchSettings(seconds=w.eval_seconds.value(), depth=w.eval_depth.value(),
                                mode="Time + depth", threads=1, hash_mb=32, multipv=1,
                                engine_id=entry.identity, engine_kind=entry.kind, predict_continuations=False)
        self.output.setPlainText(f"Comparing moves with {entry.label}…")
        self.job = job = EngineJob()
        job.session = self.session
        generation = self.generation
        board = board.copy()

        def search():
            try:
                baseline = job.run(command, board, limits)
                if job.cancelled.is_set():
                    return
                result = baseline if count == 1 else job.run(command, board, replace(limits, multipv=count))
                if job.cancelled.is_set():
                    return
                lead = baseline.get("evaluation") or baseline["lines"][0]
                rows = comparison_rows(lead, result["lines"], board.turn)
                if not rows:
                    raise ValueError("This engine did not return scored moves.")
                value = {"fen": board.fen(), "engine": result["engine"],
                         "side": "White" if board.turn else "Black",
                         "baseline": score_text(lead, 1 if board.turn else -1), "rows": rows}
                self.completed.emit(generation, value, "")
            except Exception as error:
                if not job.cancelled.is_set():
                    self.completed.emit(generation, None, str(error))

        Thread(target=search, daemon=True, name="BoardLens-move-advantage").start()

    def finish(self, generation, result, error):
        if generation != self.generation:
            return
        self.job = None
        self.result = result
        if error:
            self.output.setPlainText(error)
            return
        header = escape(f"{result['engine']} · {result['side']} to move · Current {result['baseline']}")
        rows = "".join(
            "<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                escape(row["move"]), escape(row["score"]), escape(row["change"]))
            for row in result["rows"]
        )
        self.output.setHtml(f"<p>{header}</p><table cellspacing='10'>"
                            f"<tr><th>Move</th><th>After</th><th>Change</th></tr>{rows}</table>")

    def clear(self):
        self.generation += 1
        if self.job:
            self.job.cancel()
        if self.key is not None:
            self.output.setPlainText("Waiting for a playable position.")
        self.key = self.job = self.result = None

    def close_engine(self):
        self.clear()
        self.session.close()
