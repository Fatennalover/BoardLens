"""Desktop Coach cards for the current board and its engine suggestions."""

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from .ui_controls import ResponsiveScrollArea


PIECES = Path(__file__).parent / "assets" / "pieces" / "studio"
COACH_STYLE = """
QScrollArea#coachPane, QWidget#coachContent { background:#1a1828; border:0; }
QLabel { background:transparent; }
QFrame#coachHero {
    background:qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #392452, stop:1 #241e3a);
    border:1px solid #594475; border-radius:13px;
}
QPushButton#coachMove, QPushButton#coachTopMove {
    background:#211c30; border:1px solid #413753; border-radius:12px; padding:0;
}
QPushButton#coachTopMove { background:#29203b; border-color:#8565ac; }
QPushButton#coachMove:hover, QPushButton#coachTopMove:hover,
QPushButton#coachMove:focus, QPushButton#coachTopMove:focus { border-color:#b193d9; }
QPushButton#coachMove:checked, QPushButton#coachTopMove:checked {
    background:#39274b; border-color:#eab1ff;
}
QLabel#coachHeading { font-size:22px; font-weight:700; color:#faf5ff; }
QLabel#coachMoveName { font-size:23px; font-weight:700; color:#fff8ff; }
QLabel#coachDetail { font-size:14px; color:#e4dcf4; }
QLabel#coachMuted { font-size:13px; color:#c8b9df; }
QLabel#coachTop { font-size:12px; font-weight:700; color:#d9baff; }
QLabel#coachScore, QLabel#coachPiece {
    background:#3b2d55; border:1px solid #655082; border-radius:8px;
}
QLabel#coachScore { padding:5px 9px; font-size:14px; font-weight:700; color:#f0deff; }
QFrame#coachReply { background:#1d3039; border-radius:8px; }
QLabel#coachReplyTitle { font-size:12px; font-weight:700; color:#aee3df; }
QLabel#coachReplyText { font-size:14px; color:#e2f6f4; }
QPushButton#coachAction { background:#d8baff; color:#221436; font-weight:700; border-color:#d8baff; }
QPushButton#coachAction:hover { background:#ead6ff; }
"""


def _label(name, text=""):
    label = QLabel(text)
    label.setObjectName(name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


class _MoveCard(QPushButton):
    def __init__(self):
        super().__init__()
        self.setObjectName("coachMove")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Preview this move on the board. Click again to hide the arrow.")
        body = QVBoxLayout(self)
        body.setContentsMargins(13, 11, 13, 11)
        body.setSpacing(7)

        header = QHBoxLayout()
        header.setSpacing(9)
        self.piece = _label("coachPiece")
        self.piece.setFixedSize(40, 40)
        self.piece.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self.piece)
        name = QVBoxLayout()
        name.setSpacing(0)
        self.top = _label("coachTop", "Top suggestion")
        self.move_name = _label("coachMoveName")
        name.addWidget(self.top)
        name.addWidget(self.move_name)
        header.addLayout(name, 1)
        self.score = _label("coachScore")
        header.addWidget(self.score)
        body.addLayout(header)
        self.description = _label("coachDetail")
        body.addWidget(self.description)
        self.insight = _label("coachMuted")
        body.addWidget(self.insight)

        self.reply = QFrame()
        self.reply.setObjectName("coachReply")
        reply = QVBoxLayout(self.reply)
        reply.setContentsMargins(10, 6, 10, 7)
        reply.setSpacing(2)
        self.reply_title = _label("coachReplyTitle")
        reply.addWidget(self.reply_title)
        self.reply_text = _label("coachReplyText")
        reply.addWidget(self.reply_text)
        body.addWidget(self.reply)
        self.continuation = _label("coachMuted")
        body.addWidget(self.continuation)
        for widget in self.findChildren(QWidget):
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.uci = ""
        self._move = None
        self._perspective = ""

    def sizeHint(self):
        layout = self.layout()
        return layout.sizeHint() if layout else super().sizeHint()

    def minimumSizeHint(self):
        layout = self.layout()
        return layout.minimumSize() if layout else super().minimumSizeHint()

    def set_move(self, move, perspective):
        if self._move == move and self._perspective == perspective:
            return
        top = move["rank"] == 1
        name = "coachTopMove" if top else "coachMove"
        if self.objectName() != name:
            self.setObjectName(name)
            self.style().unpolish(self)
            self.style().polish(self)
        self.top.setVisible(top)
        self.move_name.setText(move["san"])
        self.uci = move["uci"]
        self.setAccessibleName(f"Preview {move['san']}")
        symbol = move["piece"]
        if not self._move or self._move["piece"] != symbol:
            color = "w" if symbol.isupper() else "b"
            icon = QIcon(str(PIECES / f"{color}{symbol.lower()}.png"))
            self.piece.setPixmap(icon.pixmap(QSize(30, 30), self.devicePixelRatioF()))
            self.piece.setVisible(bool(symbol))
        score = move["score"]
        self.score.setText(score)
        self.score.setVisible(bool(score and score != "—"))
        self.score.setToolTip(f"Estimated score for {perspective} after this move")
        self.description.setText(move["description"])
        self.description.setVisible(bool(move["description"]))
        self.insight.setText(move["insights"])
        self.insight.setVisible(bool(move["insights"]))
        reply = move["reply_simple"]
        self.reply_title.setText("Likely reply" if reply else "Reply")
        self.reply_text.setText(reply.replace(": ", " · ", 1) if reply else move["reply_status"])
        self.reply.setVisible(bool(reply or move["reply_status"]))
        self.continuation.setText(f"Line · {move['continuation']}")
        self.continuation.setVisible(bool(move["continuation"]))
        self._move = move
        self._perspective = perspective


class CoachPane(ResponsiveScrollArea):
    preview_changed = Signal()

    def __init__(self, suggest, settings):
        content = QWidget()
        content.setObjectName("coachContent")
        layout = QVBoxLayout(content)
        super().__init__(content)
        self.setObjectName("coachPane")
        self.setAccessibleName("Coach guidance")
        self.setStyleSheet(COACH_STYLE)
        self._layout = layout
        self._layout.setContentsMargins(4, 7, 6, 8)
        self._layout.setSpacing(9)
        self._cards = []
        self._guidance = None
        self._preview = None

        hero = QFrame()
        hero.setObjectName("coachHero")
        hero.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(13, 12, 13, 12)
        hero_layout.setSpacing(6)
        heading = QHBoxLayout()
        self.heading = _label("coachHeading")
        self.position_score = _label("coachScore")
        heading.addWidget(self.heading, 1)
        heading.addWidget(self.position_score)
        hero_layout.addLayout(heading)
        self.position_summary = _label("coachDetail")
        hero_layout.addWidget(self.position_summary)
        self.engine = _label("coachMuted")
        hero_layout.addWidget(self.engine)
        self.status = _label("coachDetail")
        hero_layout.addWidget(self.status)
        self.suggest_button = QPushButton("Suggest moves")
        self.suggest_button.setObjectName("coachAction")
        self.suggest_button.clicked.connect(suggest)
        actions = QHBoxLayout()
        actions.addWidget(self.suggest_button)
        actions.addStretch()
        self.settings_button = QPushButton("Coach settings…")
        self.settings_button.clicked.connect(settings)
        actions.addWidget(self.settings_button)
        hero_layout.addLayout(actions)
        self._layout.addWidget(hero)
        self._layout.addStretch()

    def preview_for(self, fen):
        if self._preview and self._preview[0] == fen:
            moves = (self._guidance[1] or {}).get("moves", ())
            return next((move for move in moves if move["uci"] == self._preview[1]), None)
        return None

    def _toggle_preview(self, uci):
        selection = (self._guidance[0], uci)
        if selection == self._preview:
            self.clear_preview()
            return
        self._preview = selection
        for card in self._cards:
            card.setChecked(card.uci == uci)
        self.preview_changed.emit()

    def clear_preview(self):
        if self._preview is not None:
            self._preview = None
            for card in self._cards:
                card.setChecked(False)
            self.preview_changed.emit()

    def set_guidance(self, fen, snapshot=None, *, title="", status="", perspective="", move_type="", can_suggest=False):
        guidance = (fen, snapshot, title, status, perspective, move_type, can_suggest)
        if guidance == self._guidance:
            return
        if not self._guidance or self._guidance[0] != fen:
            self.verticalScrollBar().setValue(0)
        previous_preview = self.preview_for(fen)
        self._guidance = guidance
        snapshot = snapshot or {}
        self.heading.setText(f"{snapshot['side']} to move" if snapshot else title)
        score = snapshot.get("score", "")
        has_score = bool(score and score != "—")
        self.position_score.setText(f"{score} for {perspective}")
        self.position_score.setVisible(has_score)
        evaluator = snapshot.get("evaluator", "")
        summary = " · ".join(filter(None, (snapshot.get("position_summary"), evaluator))) if has_score else ""
        self.position_summary.setText(summary)
        self.position_summary.setVisible(bool(summary))
        engine = snapshot.get("engine", "")
        detail = " · ".join(filter(None, (f"Suggestions from {engine}" if engine else "", move_type)))
        self.engine.setText(detail)
        self.engine.setVisible(bool(engine and (not has_score or engine != evaluator or move_type)))
        self.status.setText(status)
        self.status.setVisible(bool(status))
        self.suggest_button.setVisible(can_suggest)
        moves = snapshot.get("moves", ())
        preview = self.preview_for(fen)
        while len(self._cards) < len(moves):
            card = _MoveCard()
            card.clicked.connect(lambda _, button=card: self._toggle_preview(button.uci))
            self._layout.insertWidget(self._layout.count() - 1, card)
            self._cards.append(card)
        for card, move in zip(self._cards, moves):
            card.set_move(move, perspective)
            card.setChecked(preview is not None and card.uci == preview["uci"])
            card.show()
        for card in self._cards[len(moves):]:
            card.hide()
        if self._preview and preview is None:
            self.clear_preview()
        elif preview and previous_preview and preview["reply_uci"] != previous_preview["reply_uci"]:
            self.preview_changed.emit()
