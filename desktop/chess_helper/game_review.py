"""Browse recorded moves and engine continuations on an independent board."""
from __future__ import annotations

from dataclasses import replace
from threading import Thread

import chess
from PySide6.QtCore import QObject, QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QGridLayout, QLabel, QListWidget,
                               QPushButton, QSplitter, QVBoxLayout, QWidget)

from . import engine_config, engine_library
from .engine import EngineJob, EngineSession
from .widgets import BoardArea, BoardView, EvalBar


CONTINUATION_PLIES = 100


class MoveLine:
    def __init__(self, board, moves=()):
        self.start = board.copy()
        self.tail = board.copy()
        self.moves = []
        self.labels = ["Starting position"]
        self.results = {}
        for move in moves:
            self.append(move)

    def append(self, move):
        separator = "." if self.tail.turn else "…"
        self.labels.append(f"{self.tail.fullmove_number}{separator} {self.tail.san(move)}")
        self.moves.append(move)
        self.tail.push(move)

    def position(self, index):
        board = self.start.copy()
        for move in self.moves[:index]:
            board.push(move)
        return board


def outcome_text(outcome):
    if outcome is None:
        return ""
    reason = outcome.termination.name.lower().replace("_", " ")
    if outcome.winner is None:
        return f"Draw · {reason}"
    return f"{'White' if outcome.winner else 'Black'} wins · {reason}"


class ReviewSignals(QObject):
    position = Signal(int, int, object, object)
    completed = Signal(int, str)


class GameReview(QDialog):
    def __init__(self, workspace, board, start_at=None):
        super().__init__(workspace)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("BoardLens · Game review")
        self.resize(920, 630)
        self.workspace = workspace
        self.white_bottom = workspace.white_bottom
        self.played = MoveLine(board.root(), board.move_stack)
        self.line = self.played
        self.continuation = None
        self.generation = 0
        self.job = None

        self.signals = ReviewSignals(self)
        self.signals.position.connect(self.accept_position)
        self.signals.completed.connect(self.finish)

        root = QVBoxLayout(self)
        actions = QGridLayout()
        self.engine = QComboBox()
        self.engine.setAccessibleName("Review engine")
        current = workspace.engine_kind.currentIndex()
        for index, entry in enumerate(engine_library.ENTRIES):
            if index in (0, current) or engine_library.available(entry):
                self.engine.addItem(entry.label, index)
        self.engine.setCurrentIndex(self.engine.findData(current))
        self.engine.currentIndexChanged.connect(self.clear_results)
        self.analyze = QPushButton("Analyze game")
        self.analyze.setToolTip("Analyze every recorded position with the chosen engine.")
        self.analyze.clicked.connect(lambda: self.start(False))
        self.play_out = QPushButton("Play out from here")
        self.play_out.setToolTip("Let the chosen engine play both sides for up to 50 moves.")
        self.play_out.clicked.connect(lambda: self.start(True))
        self.cancel_button = QPushButton("Stop")
        self.cancel_button.clicked.connect(self.cancel)
        actions.addWidget(QLabel("Engine"), 0, 0)
        actions.addWidget(self.engine, 0, 1, 1, 3)
        for col, button in enumerate((self.analyze, self.play_out, self.cancel_button), 1):
            actions.addWidget(button, 1, col)
        root.addLayout(actions)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        self.view = BoardView()
        self.view.setToolTip("Position after the selected move. Lavender shows the next recorded move when it differs from the engine suggestion.")
        self.view.setAccessibleName("Review board")
        self.eval_bar = EvalBar()
        self.eval_bar.hold_last_score = False
        split.addWidget(BoardArea(self.view, self.eval_bar))
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(6, 0, 0, 0)
        self.line_picker = QComboBox()
        self.line_picker.setAccessibleName("Move list")
        self.line_picker.addItem("Played moves")
        self.line_picker.currentIndexChanged.connect(self.select_line)
        self.moves = QListWidget()
        self.moves.setAccessibleName("Review moves")
        self.moves.currentRowChanged.connect(self.show_position)
        right_layout.addWidget(self.line_picker)
        right_layout.addWidget(self.moves, 1)
        controls = QGridLayout()
        self.previous = QPushButton("Previous")
        self.previous.clicked.connect(lambda: self.moves.setCurrentRow(self.moves.currentRow() - 1))
        self.next = QPushButton("Next")
        self.next.clicked.connect(lambda: self.moves.setCurrentRow(self.moves.currentRow() + 1))
        controls.addWidget(self.previous, 0, 0)
        controls.addWidget(self.next, 0, 1)
        right_layout.addLayout(controls)
        split.addWidget(right)
        split.setSizes([560, 310])
        root.addWidget(split, 1)

        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.details)
        self.variation = QLabel()
        self.variation.setWordWrap(True)
        self.variation.setTextFormat(Qt.TextFormat.PlainText)
        self.variation.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.variation)
        self.progress = QLabel("Select a move to see its position." if self.played.moves else
                               "No earlier moves are known. Play out a continuation from this position.")
        self.progress.setWordWrap(True)
        self.progress.setTextFormat(Qt.TextFormat.PlainText)
        root.addWidget(self.progress)
        self.fill_moves(len(self.played.moves) if start_at is None else start_at)
        workspace.overlay_enabled.toggled.connect(self.refresh_position)

    def matches(self, board):
        return self.played.tail.fen() == board.fen() and self.played.moves == board.move_stack

    def reopen(self, start_at):
        if start_at is not None:
            self.line_picker.setCurrentIndex(0)
            self.moves.setCurrentRow(min(start_at, self.moves.count() - 1))
        self.show()
        self.raise_()
        self.activateWindow()

    def refresh_position(self):
        self.show_position(self.moves.currentRow())

    def fill_moves(self, row):
        with QSignalBlocker(self.moves):
            self.moves.clear()
            self.moves.addItems(self.line.labels)
            self.moves.setCurrentRow(max(0, min(row, self.moves.count() - 1)))
        self.show_position(self.moves.currentRow())

    def select_line(self, index):
        self.line = self.continuation if index == 1 and self.continuation else self.played
        self.fill_moves(0)

    def clear_results(self):
        self.played.results.clear()
        # The simulated line retains the engine that generated it.
        self.refresh_position()

    def show_position(self, index):
        if index < 0:
            return
        board = self.line.position(index)
        self.view.set_position(board, self.white_bottom)
        score = self.line.results.get(index) or {}
        outcome = board.outcome(claim_draw=self.line is self.continuation)
        result = outcome_text(outcome)
        self._can_play = outcome is None
        turn = "White" if board.turn else "Black"
        self.details.setText(result or (f"{turn} to move · {score['engine']} · {score['score']} · "
                                        f"{score['description']}" if score else f"{turn} to move"))
        variation = score.get("pv")
        self.variation.setText(f"Engine line · {variation}" if variation else "")
        self.variation.setVisible(bool(variation))
        self.eval_bar.white_bottom = self.white_bottom
        self.eval_bar.cp = score.get("cp")
        self.eval_bar.mate = score.get("mate")
        self.eval_bar.white_share = score.get("white_share")
        if outcome is not None:
            self.eval_bar.cp = {None: 0, chess.WHITE: 100000, chess.BLACK: -100000}[outcome.winner]
        self.eval_bar.update()
        self.view.arrows = []
        self.view.overlap_color = self.workspace.overlap_color
        if not result and self.workspace.overlay_enabled.isChecked():
            if score and score.get("move"):
                move = chess.Move.from_uci(score["move"])
                self.view.arrows.append({"move": move, "color": self.workspace.extra_engines.primary_color})
            if index < len(self.line.moves):
                played = self.line.moves[index]
                if not score or played.uci() != score.get("move"):
                    self.view.arrows.append({"move": played, "color": "#ad93e3"})
        self.view.update()
        self.previous.setEnabled(index > 0)
        self.next.setEnabled(index < len(self.line.moves))
        self.set_busy(self.job is not None)

    def set_busy(self, busy):
        self.engine.setEnabled(not busy)
        self.analyze.setEnabled(not busy)
        self.play_out.setEnabled(not busy and self._can_play)
        self.cancel_button.setEnabled(busy)

    def start(self, simulate):
        engine_index = self.engine.currentData()
        try:
            path = engine_config.command(self.workspace, engine_index)
        except (ValueError, OSError) as error:
            self.progress.setText(str(error))
            return
        entry = engine_library.selected(engine_index)
        settings = self.workspace.search_settings()
        same_engine = engine_index == self.workspace.engine_kind.currentIndex()
        settings = replace(settings, multipv=1, predict_continuations=False, engine_id=entry.identity,
                           engine_kind=entry.identity if entry.kind == "tiny" else entry.kind,
                           mode=self.workspace.mode.currentText(),
                           strength=settings.strength if same_engine else "Full strength",
                           style=settings.style if same_engine else "Balanced")
        start_board = self.line.position(self.moves.currentRow()) if simulate else self.played.start.copy()
        played = () if simulate else tuple(self.played.moves)
        if simulate:
            self.continuation = MoveLine(start_board)
            with QSignalBlocker(self.line_picker):
                if self.line_picker.count() == 1:
                    self.line_picker.addItem("Engine continuation")
                self.line_picker.setItemText(1, f"Continuation · {entry.label}")
                self.line_picker.setCurrentIndex(1)
            self.line = self.continuation
            self.fill_moves(0)
        else:
            self.played.results.clear()
            self.line_picker.setCurrentIndex(0)
        self.generation += 1
        self.job = job = EngineJob()
        generation = self.generation
        self.job_line = self.continuation if simulate else self.played
        self.refresh_position()
        self.progress.setText("Analyzing with " + entry.label + "…")
        Thread(target=self.run, args=(generation, job, path, settings, start_board, played, simulate),
               daemon=True, name="BoardLens-game-review").start()

    def run(self, generation, job, path, settings, board, played, simulate):
        session = job.session = EngineSession()
        maximum = CONTINUATION_PLIES if simulate else len(played) + 1
        message = "Game analysis complete"
        try:
            for index in range(maximum):
                if job.cancelled.is_set():
                    return
                outcome = board.outcome(claim_draw=simulate)
                if outcome is not None:
                    message = outcome_text(outcome)
                    break
                result = job.run(path, board, settings)
                if job.cancelled.is_set():
                    return
                if not result:
                    raise ValueError("The engine returned no analysis.")
                score = dict(result["lines"][0], engine=result["engine"])
                move = chess.Move.from_uci(score["move"]) if simulate else None
                if move is not None and move not in board.legal_moves:
                    raise ValueError("The engine returned an illegal move.")
                self.signals.position.emit(generation, index, score, move)
                if simulate:
                    board.push(move)
                elif index < len(played):
                    board.push(played[index])
            if simulate:
                message = (outcome_text(board.outcome(claim_draw=True))
                           or f"Continuation paused after {CONTINUATION_PLIES // 2} moves")
        except Exception as error:
            message = "Could not analyze: " + str(error)
        finally:
            session.close()
        if not job.cancelled.is_set():
            try:
                self.signals.completed.emit(generation, message)
            except RuntimeError:
                pass

    def accept_position(self, generation, index, score, move):
        if generation != self.generation or not self.job:
            return
        self.job_line.results[index] = score
        if move is not None:
            self.job_line.append(move)
            if self.line is self.job_line:
                self.moves.addItem(self.line.labels[-1])
        if self.line is self.job_line and self.moves.currentRow() == index:
            self.show_position(self.moves.currentRow())
        self.progress.setText(f"Analyzed {index + 1} positions · {score['engine']}")

    def finish(self, generation, message):
        if generation != self.generation:
            return
        self.job = None
        self.progress.setText(message)
        self.show_position(self.moves.currentRow())

    def cancel(self):
        if self.job:
            self.job.cancel()
            self.generation += 1
            self.job = None
            self.progress.setText("Stopped. Select any analyzed position to review it.")
            self.show_position(self.moves.currentRow())

    def done(self, result):
        self.cancel()
        super().done(result)

    def closeEvent(self, event):
        self.cancel()
        super().closeEvent(event)
