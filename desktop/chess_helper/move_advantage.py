"""Compare top moves with a separate, bounded engine search."""
from dataclasses import replace
from html import escape
import math
from threading import Thread

import chess
from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QTextBrowser, QVBoxLayout, QWidget,
)

from . import engine_config, engine_library
from .core import SearchSettings
from .engine import EngineJob, EngineSession
from .studio import ArrowColorButton
from .toggle import ToggleButton
from .ui_controls import ResponsiveScrollArea


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
        change = "—"
        score = score_text(line, sign)
        model_share = line.get("white_share")
        if model_share is not None:
            score = f"{(model_share if white_to_move else 1 - model_share):.1%}"
            current = baseline.get("white_share")
            if current is not None:
                difference = round(100 * sign * (model_share - current), 1)
                change = f"{difference:+.1f} pp" if difference else "0.0 pp"
        elif baseline.get("mate") is None and line.get("mate") is None:
            if baseline.get("cp") is not None and line.get("cp") is not None:
                difference = sign * (line["cp"] - baseline["cp"])
                change = f"{difference / 100:+.2f}" if difference else "0.00"
        elif baseline.get("mate") != line.get("mate") and (line.get("cp") is not None or line.get("mate") is not None):
            change = "Mate changes"
        row = {"move": line["san"], "score": score, "change": change}
        if line.get("move"):
            row["uci"] = line["move"]
        rows.append(row)
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
        page = QWidget()
        content = QVBoxLayout(page)
        self.options = options = QFormLayout()
        options.setVerticalSpacing(5)
        self.engine = QComboBox()
        for index, item in enumerate(engine_library.ENTRIES):
            self.engine.addItem(item.label, index)
        self.count = QSpinBox()
        self.count.setRange(0, MAX_MOVES)
        self.count.setSpecialValueText("Off")
        self.count.setToolTip("Number of moves ranked by this engine, independent of Analysis candidates.")
        self.mode = QComboBox()
        self.mode.setAccessibleName("Scoring search limit")
        self.mode.addItems(["Time + depth", "Time", "Depth"])
        self.seconds = QDoubleSpinBox()
        self.seconds.setAccessibleName("Scoring time budget")
        self.seconds.setRange(.1, 30)
        self.seconds.setValue(.3)
        self.seconds.setSingleStep(.1)
        self.seconds.setSuffix(" s")
        self.seconds.setKeyboardTracking(False)
        self.seconds.setToolTip("Time budget per search for the scoring engine.")
        self.depth = QSpinBox()
        self.depth.setAccessibleName("Scoring search depth")
        self.depth.setRange(1, 60)
        self.depth.setValue(18)
        self.depth.setKeyboardTracking(False)
        self.depth.setToolTip("How many plies ahead the scoring engine searches.")
        self.inference_note = QLabel("Uses one model prediction per search.")
        self.show_scores = ToggleButton("Gain arrows")
        self.show_scores.setToolTip("Show an arrow with the estimated gain for moves with a positive change.")
        self.score_color = ArrowColorButton("#53c6df", "Gain arrow color")
        self.show_scores.toggled.connect(self.redraw)
        self.score_color.color_changed.connect(self.redraw)
        options.addRow("Scoring engine", self.engine)
        options.addRow("Moves to compare", self.count)
        options.addRow("Search limit", self.mode)
        limits = QHBoxLayout()
        limits.setSpacing(8)
        self.time_label = QLabel("Time")
        self.time_label.setBuddy(self.seconds)
        self.depth_label = QLabel("Depth")
        self.depth_label.setBuddy(self.depth)
        limits.addWidget(self.time_label)
        limits.addWidget(self.seconds, 1)
        limits.addWidget(self.depth_label)
        limits.addWidget(self.depth, 1)
        options.addRow(limits)
        options.addRow(self.inference_note)
        content.addLayout(options)

        label_style = QDialog(self)
        label_style.setWindowTitle("Gain arrow style")
        label_style.setModal(True)
        style_form = QFormLayout(label_style)
        style_form.addRow("Arrow color", self.score_color)
        done = QPushButton("Done")
        done.clicked.connect(label_style.accept)
        style_form.addRow(done)

        display = QHBoxLayout()
        display.addWidget(self.show_scores, 1)
        style_button = QPushButton("Arrow style…")
        style_button.clicked.connect(label_style.show)
        display.addWidget(style_button)
        content.addLayout(display)

        self.output = QTextBrowser()
        self.output.setAccessibleName("Move advantage results")
        self.output.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.output.document().documentLayout().documentSizeChanged.connect(
            lambda size: self.output.setMinimumHeight(max(118, math.ceil(size.height()) + 10))
        )
        content.addWidget(self.output, 1)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(ResponsiveScrollArea(page))
        self.completed.connect(self.finish)
        self.count.valueChanged.connect(self.changed)
        self.engine.currentIndexChanged.connect(self.changed)
        self.mode.currentIndexChanged.connect(self.changed)
        self.seconds.valueChanged.connect(self.changed)
        self.depth.valueChanged.connect(self.changed)
        self.update_search_controls()
        self.output.setPlainText("Choose how many moves to compare.")

    def restore_limits(self, settings):
        with QSignalBlocker(self.mode), QSignalBlocker(self.seconds), QSignalBlocker(self.depth):
            self.mode.setCurrentText(settings.get("advantage_mode", "Time + depth"))
            self.seconds.setValue(settings.get("advantage_seconds", self.workspace.eval_seconds.value()))
            self.depth.setValue(settings.get("advantage_depth", self.workspace.eval_depth.value()))
        self.update_search_controls()

    def update_search_controls(self):
        kind = engine_library.ENTRIES[self.engine.currentData()].kind
        prediction = engine_config.is_human(self.workspace, self.engine.currentData())
        time_only = kind in ("tiny", "toby")
        mode = "Time" if time_only else self.mode.currentText()
        self.options.setRowVisible(self.mode, not (prediction or time_only))
        self.options.setRowVisible(self.inference_note, prediction)
        has_time = not prediction and mode != "Depth"
        has_depth = not prediction and mode != "Time"
        self.time_label.setVisible(has_time)
        self.seconds.setVisible(has_time)
        self.depth_label.setVisible(has_depth)
        self.depth.setVisible(has_depth)

    def redraw(self, *_):
        self.workspace.queue_autosave()
        self.workspace.update_visuals()

    def marks(self, board):
        if not self.show_scores.isChecked() or not self.result or self.result["fen"] != board.fen():
            return []
        return [
            {"square": chess.Move.from_uci(row["uci"]).to_square, "kind": "gain_arrow",
             "move": row["uci"], "color": self.score_color.color, "label": row["change"]}
            for row in self.result["rows"] if row.get("uci") and row["change"].startswith("+")
        ]

    def changed(self, *_):
        self.update_search_controls()
        self.workspace.queue_autosave()
        self.refresh()
        self.workspace.update_visuals()

    def refresh(self):
        w = self.workspace
        count = self.count.value()
        board = w.tracker.board if w.editable_position or w._reviewing or w._screen_confirmed else None
        if not count or board is None or not board.is_valid() or board.is_game_over() or w.game_ended:
            self.clear()
            self.output.setPlainText("Choose how many moves to compare." if not count else "Waiting for a playable position.")
            return
        index = self.engine.currentData()
        entry = engine_library.ENTRIES[index]
        limits = SearchSettings(seconds=self.seconds.value(), depth=self.depth.value(),
                                mode=self.mode.currentText(), threads=1, hash_mb=32, multipv=1,
                                engine_id=entry.identity, engine_kind=entry.identity if entry.kind == "tiny" else entry.kind,
                                human_elo=w.human_elo.value(), predict_continuations=False)
        key = (board.fen(), index, count, limits, w.engine_path.text(), w.custom_engine.text())
        if self.key == key:
            return
        self.clear()
        self.key = key
        try:
            command = engine_config.command(w, index)
        except (ValueError, OSError) as error:
            self.output.setPlainText(str(error))
            return
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
                lead = dict(baseline.get("evaluation") or baseline["lines"][0])
                lines = [dict(line) for line in result["lines"]]
                if entry.kind == "maia3":
                    lead["white_share"] = lead.get("expected_score")
                    for line in lines:
                        line["white_share"] = line.get("expected_score")
                elif entry.kind == "maia2":
                    if lead.get("cp") is not None:
                        lead["white_share"] = 1 / (1 + math.exp(-lead["cp"] / 400))
                    for line in lines:
                        child = board.copy()
                        child.push_uci(line["move"])
                        outcome = child.outcome()
                        if outcome:
                            line["white_share"] = .5 if outcome.winner is None else float(outcome.winner)
                        else:
                            estimate = job.run(command, child, limits)
                            if job.cancelled.is_set():
                                return
                            value = (estimate.get("evaluation") or estimate["lines"][0]).get("cp")
                            if value is not None:
                                line["white_share"] = 1 / (1 + math.exp(-value / 400))
                rows = comparison_rows(lead, lines, board.turn)
                if not rows:
                    raise ValueError("This engine did not return candidate moves.")
                sign = 1 if board.turn else -1
                baseline_text = score_text(lead, sign)
                if lead.get("white_share") is not None:
                    share = lead["white_share"]
                    baseline_text = f"{(share if board.turn else 1 - share):.1%}"
                value = {"fen": board.fen(), "engine": result["engine"],
                         "side": "White" if board.turn else "Black", "baseline": baseline_text, "rows": rows}
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
        self.workspace.update_visuals()
        if error:
            self.output.setPlainText(error)
            return
        engine = escape(result["engine"])
        side = escape(result["side"])
        baseline = escape(result["baseline"])
        rows = []
        for index, row in enumerate(result["rows"]):
            background = "#29213a" if index % 2 == 0 else "#241d32"
            rows.append(
                f'<tr bgcolor="{background}"><td><strong>{escape(row["move"])}</strong></td>'
                f'<td align="right">{escape(row["score"])}</td>'
                f'<td align="right">{escape(row["change"])}</td></tr>'
            )
        status = "<p>This engine supplies moves without a numeric score.</p>" if all(
            row["score"] == "—" for row in result["rows"]) else ""
        self.output.setHtml(
            f'<p><strong>{engine}</strong><br>{side} to move · Current {baseline}</p>{status}'
            '<table width="100%" cellspacing="0" cellpadding="5" style="color:#f4ecff;">'
            '<tr style="color:#cbbce3;"><th align="left">Move</th><th align="right">After</th>'
            f'<th align="right">Change</th></tr>{"".join(rows)}</table>'
        )

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
