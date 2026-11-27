"""The desktop Coach's own engine profile and cancellable search."""

import os
import re
from dataclasses import replace
from pathlib import Path
from threading import Thread

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from . import engine_config, engine_library
from .core import MAX_LOOKAHEAD_PLIES, SearchSettings
from .engine import EngineJob, EngineSession
from .overlay import COACH_PREVIEW_COLOR, COACH_REPLY_COLOR
from .studio import ArrowColorButton


DEFAULTS = {
    "engine_id": "stockfish", "custom_path": "", "mode": "Time",
    "seconds": .35, "depth": 18, "multipv": 3, "threads": 1, "hash_mb": 64,
    "strength": "Full strength", "skill": 20, "elo": 1500, "human_elo": 1500,
    "style": "Balanced", "prediction_plies": 2, "prediction_seconds": .35, "early": True,
    "show_reply": True, "show_evaluation": True, "auto_preview": False,
    "move_color": COACH_PREVIEW_COLOR, "reply_color": COACH_REPLY_COLOR,
}
CHOICES = {
    "mode": ("Time", "Depth", "Time + depth", "Adaptive"),
    "strength": ("Full strength", "Skill level", "Elo rating"),
    "style": ("Balanced", "Aggressive", "Defensive", "Human-like", "Maximum strength"),
}
RANGES = {
    "seconds": (.1, 300.), "depth": (1, 60), "multipv": (1, 10),
    "threads": (1, max(1, os.cpu_count() or 1)), "hash_mb": (16, 4096),
    "skill": (0, 20), "elo": (580, 3190), "human_elo": (600, 2600),
    "prediction_plies": (1, MAX_LOOKAHEAD_PLIES), "prediction_seconds": (.1, 60.),
}


def coach_preferences(saved):
    if not isinstance(saved, dict):
        return dict(DEFAULTS)
    values = dict(DEFAULTS)
    identity = saved.get("engine_id")
    if isinstance(identity, str) and identity in engine_library.BY_ID:
        values["engine_id"] = identity
    if isinstance(saved.get("custom_path"), str):
        values["custom_path"] = saved["custom_path"]
    for name in ('early','show_reply','show_evaluation','auto_preview'):
        if isinstance(saved.get(name), bool):
            values[name] = saved[name]
    for name in ('move_color','reply_color'):
        if isinstance(saved.get(name), str) and re.fullmatch(r'#[0-9a-fA-F]{6}',saved[name]):
            values[name] = saved[name]
    for name, choices in CHOICES.items():
        if saved.get(name) in choices:
            values[name] = saved[name]
    for name, (minimum, maximum) in RANGES.items():
        value = saved.get(name)
        if type(value) in (int, float) and minimum <= value <= maximum:
            values[name] = type(DEFAULTS[name])(value)
    return values


class CoachSettings(QDialog):
    def __init__(self, window, preferences):
        super().__init__(window)
        self.setWindowTitle("Coach settings")
        self.resize(470, 460)
        layout = QVBoxLayout(self)
        note = QLabel("These engine settings apply to Coach.")
        note.setWordWrap(True)
        layout.addWidget(note)
        scroll=QScrollArea();scroll.setWidgetResizable(True)
        page=QWidget();scroll.setWidget(page)
        self.form = QFormLayout(page)
        self.form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        layout.addWidget(scroll,1)
        self.engine = QComboBox()
        self.engine.setAccessibleName("Coach engine")
        for entry in engine_library.ENTRIES:
            if entry.identity in ("stockfish", "custom", preferences["engine_id"]) or engine_library.available(entry):
                self.engine.addItem(entry.label, entry.identity)
        self.engine.setCurrentIndex(self.engine.findData(preferences["engine_id"]))
        self.form.addRow("Coach engine", self.engine)

        self.custom = QLineEdit(preferences["custom_path"])
        self.custom.setAccessibleName("Coach UCI executable")
        custom_row = QHBoxLayout()
        custom_row.addWidget(self.custom, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.browse)
        custom_row.addWidget(browse)
        self.custom_row = custom_row
        self.form.addRow("UCI executable", custom_row)

        labels = {
            "mode": "Search limit", "seconds": "Think time", "depth": "Depth cap",
            "multipv": "Suggestions", "strength": "Strength", "skill": "Skill level",
            "elo": "Target Elo", "human_elo": "Human rating", "style": "Playing style",
            "prediction_plies": "Lookahead length", "prediction_seconds": "Reply time",
            "threads": "CPU threads", "hash_mb": "Hash memory",
        }
        self.fields = {}
        for name, label in labels.items():
            value = preferences[name]
            if name in CHOICES:
                field = QComboBox()
                field.addItems(CHOICES[name])
                field.setCurrentText(value)
            else:
                field = QDoubleSpinBox() if isinstance(value, float) else QSpinBox()
                field.setRange(*RANGES[name])
                field.setValue(value)
                if isinstance(field, QDoubleSpinBox):
                    field.setSingleStep(.1)
                    field.setSuffix(" s")
                elif name == "hash_mb":
                    field.setSuffix(" MB")
            self.fields[name] = field
            self.form.addRow(label, field)
        self.fields["prediction_plies"].setToolTip("One ply is one side’s move. Two plies form a full move. Includes the candidate move.")
        self.early = QCheckBox("Show moves while thinking")
        self.early.setChecked(preferences["early"])
        self.form.addRow(self.early)
        self.features = {}
        for name,label in (('show_reply','Show opponent replies'),('show_evaluation','Show Coach evaluation'),
                           ('auto_preview','Automatically show the top Coach move')):
            self.features[name] = QCheckBox(label)
            self.features[name].setChecked(preferences[name])
            self.form.addRow(self.features[name])
        self.colors = {}
        for name,label in (('move_color','Coach move arrow'),('reply_color','Coach reply arrow')):
            self.colors[name] = ArrowColorButton(preferences[name],label)
            self.form.addRow(label,self.colors[name])
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        for combo in (self.engine, self.fields["mode"], self.fields["strength"]):
            combo.currentIndexChanged.connect(self.update_controls)
        self.fields["prediction_plies"].valueChanged.connect(self.update_controls)
        self.update_controls()

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a UCI executable", self.custom.text())
        if path:
            self.custom.setText(path)

    def update_controls(self, *_):
        entry = engine_library.BY_ID[self.engine.currentData()]
        kind = entry.kind
        human = engine_config.is_human(self.parent(), engine_library.ENTRIES.index(entry))
        time_only = kind in ("tiny", "toby")
        mode = self.fields["mode"].currentText()
        strength = self.fields["strength"].currentText()
        limits_strength = kind in ("stockfish", "gaia")
        self.form.setRowVisible(self.custom_row, kind == "custom")
        visible = {
            "mode": not (human or time_only),
            "seconds": not human and (time_only or mode != "Depth"),
            "depth": not (human or time_only) and mode != "Time",
            "multipv": kind != "tiny",
            "strength": limits_strength,
            "skill": limits_strength and strength == "Skill level",
            "elo": limits_strength and strength == "Elo rating",
            "human_elo": kind in ("maia2", "maia3", "allie", "flounder", "toby"),
            "style": not (human or time_only) and (not limits_strength or strength == "Full strength"),
            "prediction_seconds": self.fields["prediction_plies"].value() > 1,
            "threads": not human and kind != "tiny",
            "hash_mb": not (human or time_only),
        }
        for name, shown in visible.items():
            self.form.setRowVisible(self.fields[name], shown)
        elo_range = (580, 2640) if kind == "gaia" else (1320, 3190)
        self.fields["elo"].setRange(*elo_range)
        self.fields["skill"].setMinimum(int(kind == "gaia"))

    def accept(self):
        if self.engine.currentData() == "custom" and not Path(self.custom.text().strip()).is_file():
            QMessageBox.information(self, "Choose a Coach engine", "Select an existing UCI executable for Coach.")
            return
        super().accept()

    def preferences(self):
        values = {name: field.currentText() if isinstance(field, QComboBox) else field.value()
                  for name, field in self.fields.items()}
        values.update({name:field.isChecked() for name,field in self.features.items()})
        values.update({name:field.color for name,field in self.colors.items()})
        return dict(values, engine_id=self.engine.currentData(), custom_path=self.custom.text().strip(),
                    early=self.early.isChecked())


class CoachAnalysis(QObject):
    changed = Signal()
    partial = Signal(int, object)
    completed = Signal(int, object, str)

    def __init__(self, window, shared_searches=None):
        super().__init__(window)
        self.window = window
        self.preferences = coach_preferences(window.settings.get("coach"))
        self.session = EngineSession()
        self.shared_searches = shared_searches
        self.future = None
        self.follow = False
        self.key = self.result = self.job = None
        self.error = ""
        self.generation = 0
        self.partial.connect(self.on_partial)
        self.completed.connect(self.finish)

    def profile(self):
        values = self.preferences
        entry = engine_library.BY_ID[values["engine_id"]]
        kind = entry.kind
        index = engine_library.ENTRIES.index(entry)
        uses_strength = kind in ("stockfish", "gaia")
        strength = values["strength"] if uses_strength else "Full strength"
        settings = SearchSettings(
            engine_id=entry.identity, engine_kind=entry.identity if kind == "tiny" else kind,
            mode="Time" if kind in ("tiny", "toby") else values["mode"],
            seconds=values["seconds"], depth=values["depth"],
            multipv=1 if kind == "tiny" else values["multipv"],
            threads=values["threads"], hash_mb=values["hash_mb"],
            strength=strength, skill=values["skill"], elo=values["elo"], human_elo=values["human_elo"],
            style=values["style"] if strength == "Full strength" and kind not in ("tiny", "toby")
            and not engine_config.is_human(self.window, index) else "Balanced",
            prediction_plies=values["prediction_plies"], prediction_seconds=values["prediction_seconds"],
        )
        return index, settings

    def request(self, board, candidate_count=None):
        index, settings = self.profile()
        if candidate_count is not None and not settings.engine_kind.startswith('tiny'):
            settings = replace(settings,multipv=candidate_count)
        custom = self.preferences["custom_path"]
        history = tuple(board.move_stack) if settings.engine_kind in ("allie", "maia3") else ()
        key = (board.fen(), history, settings, custom, self.window.engine_path.text())
        if key == self.key:
            return
        self.clear()
        self.key = key
        try:
            if settings.engine_kind == "custom":
                if not Path(custom).is_file():
                    raise ValueError("Choose a UCI executable in Coach settings.")
                command = custom
            else:
                command = engine_config.command(self.window, index)
        except (OSError, ValueError) as error:
            self.error = str(error)
            return
        self.job = job = EngineJob()
        job.session = self.session
        generation = self.generation
        if self.preferences["early"]:
            job.on_update = lambda result: self.partial.emit(generation, result)
        position = board.copy()

        def search():
            try:
                result = (self.shared_searches.run(job,command,position,settings) if self.shared_searches
                          else job.run(command,position,settings))
                error = ""
            except Exception as exc:
                result, error = None, str(exc)
            if not self.session.closed:
                try:
                    self.completed.emit(generation, result, error)
                except RuntimeError:
                    pass

        if self.shared_searches:
            self.future = self.shared_searches.submit(search,0)
        else:
            Thread(target=search, daemon=True, name="BoardLens-coach").start()

    def on_partial(self, generation, result):
        if generation == self.generation:
            self.result = dict(result, provisional=True)
            self.changed.emit()

    def finish(self, generation, result, error):
        if generation == self.generation:
            self.job = None
            self.future = None
            self.result = result
            self.error = error
            self.changed.emit()

    def clear(self):
        self.generation += 1
        if self.job:
            self.job.cancel()
        if self.future:
            self.future.cancel()
            self.future = None
        self.key = self.job = self.result = None
        self.error = ""

    def close_engine(self):
        self.clear()
        self.session.close()
