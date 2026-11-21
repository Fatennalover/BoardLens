from __future__ import annotations

import math
from pathlib import Path

import chess
from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, Signal, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget, QSizePolicy
from PySide6.QtSvg import QSvgRenderer

from .capture import bgr_pixmap
from .core import cell_to_square, square_to_cell
from .overlay import DEFAULT_OVERLAP_COLOR, paint_arrows, paint_marks


class BoardView(QWidget):
    square_clicked = Signal(int)
    _studio_pieces = None
    LIGHT_TILE = "#e2ddeb"
    DARK_TILE = "#877aab"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.board = chess.Board()
        self.white_bottom = True
        self.best_move = None
        self.arrows = []
        self.overlap_color = DEFAULT_OVERLAP_COLOR
        self.marks = []
        self.selected = None
        root = Path(__file__).parent / "assets/pieces"
        self.pieces = {symbol: QSvgRenderer(str(root / (("w" if symbol.isupper() else "b") + symbol.upper() + ".svg")))
                       for symbol in "KQRBNPkqrbnp"}
        self._slide = QVariantAnimation(self)
        self._slide.setDuration(125)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide.valueChanged.connect(lambda _: self.update())
        self._slide.finished.connect(self._finish_slide)
        self._last_move = None
        self.setMinimumSize(260, 260)
        self.setToolTip("Practice mode: click a piece, then its destination. Promotions become queens.")

    def _styled_pieces(self):
        if BoardView._studio_pieces is None:
            root = Path(__file__).parent / "assets/pieces/studio"
            BoardView._studio_pieces = {
                symbol: QPixmap(str(root / (("w" if symbol.isupper() else "b") + symbol.lower() + ".png")))
                for symbol in self.pieces
            }
        return BoardView._studio_pieces

    def _finish_slide(self):
        self._last_move = None
        self.update()

    def set_position(self, board, white_bottom):
        if self.white_bottom != white_bottom or self.board.board_fen() != board.board_fen():
            self._slide.stop()
            self._last_move = None
            if white_bottom == self.white_bottom and board.move_stack and board.ply() == self.board.ply() + 1:
                move = board.peek()
                piece = self.board.piece_at(move.from_square)
                if piece and piece.color != board.turn and self.isVisible():
                    self._last_move = move
                    self._slide.setStartValue(0.0)
                    self._slide.setEndValue(1.0)
                    self._slide.start()
        self.board = board.copy(stack=False)
        self.white_bottom = white_bottom
        self.update()

    def draw_piece(self, painter, symbol, rect):
        image = self._styled_pieces()[symbol]
        if not image.isNull():
            painter.drawPixmap(rect, image, QRectF(image.rect()))
            return
        self.pieces[symbol].render(painter, rect)

    def board_rect(self):
        size = max(0,min(self.width() - 32, self.height() - 32))
        return QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.board_rect()
        if rect.width()<8:return
        cell = rect.width() / 8
        light, dark = self.LIGHT_TILE, self.DARK_TILE
        for row in range(8):
            for col in range(8):
                square = cell_to_square(row, col, self.white_bottom)
                tile = QRectF(rect.x() + col * cell, rect.y() + row * cell, cell, cell)
                p.fillRect(tile, QColor(light if (row + col) % 2 == 0 else dark))
                if square == self.selected:
                    p.fillRect(tile, QColor(247, 201, 83, 160))
                piece = self.board.piece_at(square)
                if piece and (self._last_move is None or square != self._last_move.to_square):
                    self.draw_piece(p, piece.symbol(), tile.adjusted(cell*.04, cell*.04, -cell*.04, -cell*.04))
        if self._last_move:
            move = self._last_move
            piece = self.board.piece_at(move.to_square)
            if piece:
                fraction = self._slide.currentValue() or 0
                row, col = square_to_cell(move.from_square, self.white_bottom)
                dest_row, dest_col = square_to_cell(move.to_square, self.white_bottom)
                x = rect.x() + (col + (dest_col - col) * fraction + .04) * cell
                y = rect.y() + (row + (dest_row - row) * fraction + .04) * cell
                self.draw_piece(p, piece.symbol(), QRectF(x, y, cell * .92, cell * .92))
        p.setFont(QFont("Arial", 9))
        p.setPen(QColor("#c6bed9"))
        for i in range(8):
            square = cell_to_square(7, i, self.white_bottom)
            p.drawText(QRectF(rect.x() + i * cell, rect.bottom() + 2, cell, 16),
                       Qt.AlignmentFlag.AlignCenter, chess.FILE_NAMES[chess.square_file(square)])
            rank = chess.square_rank(cell_to_square(i, 0, self.white_bottom)) + 1
            p.drawText(QRectF(rect.x() - 16, rect.y() + i * cell, 14, cell),
                       Qt.AlignmentFlag.AlignCenter, str(rank))
        paint_marks(p,rect,self.white_bottom,self.marks)
        if self.arrows:
            paint_arrows(p, rect, self.white_bottom, self.arrows, self.overlap_color)
        elif self.best_move:
            def center(square):
                row, col = square_to_cell(square, self.white_bottom)
                return QPointF(rect.x() + (col + .5) * cell, rect.y() + (row + .5) * cell)
            start, end = center(self.best_move.from_square), center(self.best_move.to_square)
            p.setPen(QPen(QColor(246, 186, 67, 215), max(4, cell * .1), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(start, end)
            angle = math.atan2(end.y() - start.y(), end.x() - start.x())
            length = cell * .30
            points = [end, QPointF(end.x() - length * math.cos(angle - .55), end.y() - length * math.sin(angle - .55)),
                      QPointF(end.x() - length * math.cos(angle + .55), end.y() - length * math.sin(angle + .55))]
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#f6ba43"))
            p.drawPolygon(QPolygonF(points))

    def mousePressEvent(self, event):
        rect = self.board_rect()
        if event.button() == Qt.MouseButton.LeftButton and rect.contains(event.position()):
            col = int((event.position().x() - rect.x()) * 8 / rect.width())
            row = int((event.position().y() - rect.y()) * 8 / rect.height())
            self.square_clicked.emit(cell_to_square(row, col, self.white_bottom))


class EvalBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(64)
        self.cp = None
        self.mate = None
        self.white_share = None
        self.white_bottom = True
        self.pending = False
        self.hold_last_score = True
        self._fraction = .5
        self._target = .5
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(200)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._animate)
        self.score_label=QLabel("—",self)
        self.score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.score_label.setStyleSheet("background:#493960;color:white;border-radius:5px;font-size:14px;font-weight:700;padding:0;")
        self.setToolTip("White's evaluation: + favors White; − favors Black. The bar shows a score, not a winning percentage.")

    def _animate(self, value):
        self._fraction = float(value)
        super().update()

    def update(self, *args):
        # An unknown/pending score retains the last fill, never a flash to 50/50.
        target = self._target if self.hold_last_score else .5
        if self.white_share is not None:
            target = self.white_share
        if self.cp is not None:
            target = 1 / (1 + math.exp(-max(-1200, min(1200, self.cp)) / 220))
        if self.mate is not None:
            target = .99 if self.mate > 0 else .01
        if target != self._target:
            self._animation.stop()
            self._target = target
            self._animation.setStartValue(self._fraction)
            self._animation.setEndValue(target)
            self._animation.start()
        super().update(*args)

    def score_text(self):
        if self.white_share is not None:return f"{self.white_share:.0%}"
        if self.mate is not None:return f"{'+' if self.mate>0 else '−'}M{abs(self.mate)}"
        if self.cp is None:return "—"
        if abs(self.cp)>=100000:return "1–0" if self.cp>0 else "0–1"
        return f"{self.cp/100:+.2f}" if abs(self.cp)<1000 else f"{self.cp/100:+.1f}"

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.score_label.setGeometry(0,max(0,(self.height()-34)//2),self.width(),34)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(10, 1, max(1,self.width() - 20), max(1,self.height() - 2))
        fraction = self._fraction
        p.fillRect(rect, QColor("#261d36"))
        white_height = rect.height() * fraction
        white_rect = QRectF(rect.x(), rect.bottom() - white_height if self.white_bottom else rect.y(), rect.width(), white_height)
        p.fillRect(white_rect, QColor("#f4ecff"))
        p.setPen(QPen(QColor("#8673a2"), 1))
        p.drawRect(rect)
        text=self.score_text()
        self.score_label.setText(text)
        self.setAccessibleName("Evaluation for White: "+text)


class BoardArea(QWidget):
    """Fit a square board and align the evaluation bar to its 64 squares."""
    def __init__(self,view,bar,parent=None):
        super().__init__(parent)
        self.view=view;self.bar=bar
        view.setParent(self);bar.setParent(self)
        view.setMinimumSize(0,0)
        self.setMinimumHeight(280)
        self.setMinimumWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)

    def sizeHint(self):return QSize(580,500)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.arrange()

    def arrange(self):
        gap=12
        side=max(1,min(self.width()-self.bar.width()-gap,self.height()))
        x=max(0,(self.width()-side-self.bar.width()-gap)//2)
        y=max(0,(self.height()-side)//2)
        self.view.setGeometry(x+self.bar.width()+gap,y,side,side)
        self.bar.setGeometry(x,y+16,self.bar.width(),max(1,side-32))


class CropCanvas(QWidget):
    def __init__(self, image, detections=None, parent=None):
        super().__init__(parent)
        self.pixmap = bgr_pixmap(image)
        self.detections = detections or []
        self.selection = None
        self.origin = None
        self.dragging = False
        self.setMinimumSize(640, 400)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def image_rect(self):
        scale = min(self.width() / self.pixmap.width(), self.height() / self.pixmap.height())
        w, h = self.pixmap.width() * scale, self.pixmap.height() * scale
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def pixel(self, point):
        rect = self.image_rect()
        return QPointF(max(0, min(self.pixmap.width() - 1, (point.x() - rect.x()) * self.pixmap.width() / rect.width())),
                       max(0, min(self.pixmap.height() - 1, (point.y() - rect.y()) * self.pixmap.height() / rect.height())))

    def paintEvent(self, event):
        p = QPainter(self)
        rect = self.image_rect()
        p.drawPixmap(rect, self.pixmap, QRectF(self.pixmap.rect()))
        scale = rect.width() / self.pixmap.width()
        if not self.selection:
            p.setPen(QPen(QColor("#c9b1ff"), 3))
            p.setBrush(QColor(35, 180, 110, 35))
            for d in self.detections:
                p.drawRect(QRectF(rect.x() + d.x * scale, rect.y() + d.y * scale, d.size * scale, d.size * scale))
        else:
            x, y, size = self.selection
            p.fillRect(rect, QColor(0, 0, 0, 95))
            dest = QRectF(rect.x() + x * scale, rect.y() + y * scale, size * scale, size * scale)
            p.drawPixmap(dest, self.pixmap, QRectF(x, y, size, size))
            p.setPen(QPen(QColor("#c9b1ff"), 2))
            p.drawRect(dest)
            for i in range(1, 8):
                p.setPen(QPen(QColor(100, 255, 170, 90), 1))
                p.drawLine(QPointF(dest.x() + dest.width() * i / 8, dest.y()), QPointF(dest.x() + dest.width() * i / 8, dest.bottom()))
                p.drawLine(QPointF(dest.x(), dest.y() + dest.height() * i / 8), QPointF(dest.right(), dest.y() + dest.height() * i / 8))

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.image_rect().contains(event.position()):
            return
        self.origin = self.pixel(event.position())
        self.dragging = False

    def mouseMoveEvent(self, event):
        if self.origin is None or not event.buttons() & Qt.MouseButton.LeftButton:
            return
        point = self.pixel(event.position())
        dx, dy = point.x() - self.origin.x(), point.y() - self.origin.y()
        size = int(min(abs(dx), abs(dy)))
        if size > 5:
            self.dragging = True
            self.selection = (int(self.origin.x() if dx > 0 else self.origin.x() - size),
                              int(self.origin.y() if dy > 0 else self.origin.y() - size), size)
            self.update()

    def mouseReleaseEvent(self, event):
        if self.origin is None:
            return
        if not self.dragging:
            point = self.pixel(event.position())
            for d in self.detections:
                if d.x <= point.x() <= d.x + d.size and d.y <= point.y() <= d.y + d.size:
                    self.selection = (d.x, d.y, d.size)
                    break
        self.origin = None
        self.update()


class CropDialog(QDialog):
    def __init__(self, image, detections=None, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QDialogButtonBox
        self.setWindowTitle("Select the 64 squares")
        self.resize(1040, 700)
        layout = QVBoxLayout(self)
        text = "Click a green detected board, or drag from one corner to the opposite corner. Include only the 64 squares."
        label = QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.canvas = CropCanvas(image, detections)
        layout.addWidget(self.canvas, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        if self.canvas.selection and self.canvas.selection[2] >= 80:
            super().accept()
