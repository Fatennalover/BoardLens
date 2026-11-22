"""Click-through, per-monitor arrows. Never receives board clicks or focus."""
from __future__ import annotations

import math
import os
import sys

import chess

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPainterPathStroker, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from .core import square_to_cell


DEFAULT_OVERLAP_COLOR = "#a855f7"


def paint_arrows(painter, rect, white_bottom, arrows, overlap_color=DEFAULT_OVERLAP_COLOR):
    if not arrows or rect.isEmpty():
        return
    cell = rect.width() / 8
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    shapes = []
    labels = []
    overlaps = QPainterPath()
    for arrow in sorted(arrows, key=lambda candidate: not candidate.get("reply", False)):
        move = arrow["move"]
        projected = arrow.get("points") or {}

        def point(square):
            if square in projected:
                x, y = projected[square]
                return QPointF(rect.x() + x * rect.width(), rect.y() + y * rect.height())
            row, col = square_to_cell(square, white_bottom)
            return QPointF(rect.x() + (col + .5) * cell, rect.y() + (row + .5) * cell)

        start, end = point(move.from_square), point(move.to_square)
        color = QColor(arrow["color"])
        color.setAlpha(215)
        style = Qt.PenStyle.DashLine if arrow.get("dashed") else Qt.PenStyle.SolidLine
        pen = QPen(color, max(3, cell * .095), style, Qt.PenCapStyle.RoundCap)
        shaft = QPainterPath(start)
        dx, dy = abs(end.x() - start.x()) / cell, abs(end.y() - start.y()) / cell
        tail = start
        if not projected and (round(dx), round(dy)) in ((1, 2), (2, 1)):
            tail = QPointF(end.x(), start.y()) if dx > dy else QPointF(start.x(), end.y())
            shaft.lineTo(tail)
            shaft.moveTo(tail)
        shaft.lineTo(end)

        angle = math.atan2(end.y() - tail.y(), end.x() - tail.x())
        length = cell * .29
        head = QPainterPath()
        head.addPolygon(QPolygonF([end,
            QPointF(end.x() - length * math.cos(angle - .52), end.y() - length * math.sin(angle - .52)),
            QPointF(end.x() - length * math.cos(angle + .52), end.y() - length * math.sin(angle + .52))]))
        head.closeSubpath()
        shape = QPainterPathStroker(pen).createStroke(shaft).united(head)
        painter.fillPath(shape, color)
        bounds = shape.boundingRect()
        for other, other_bounds in shapes:
            if bounds.intersects(other_bounds):
                overlaps = overlaps.united(shape.intersected(other))
        shapes.append((shape, bounds))

        if arrow.get("label"):
            labels.append((arrow["label"], start * .28 + end * .72, color))

    painter.fillPath(overlaps, QColor(overlap_color))
    radius = max(9, cell * .16)
    for label, center, color in labels:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#152630"))
        painter.drawEllipse(center, radius, radius)
        painter.setPen(color.lighter(130))
        painter.setFont(QFont("Arial", max(8, round(radius * .8)), QFont.Weight.Bold))
        painter.drawText(QRectF(center.x() - radius, center.y() - radius, 2 * radius, 2 * radius),
                         Qt.AlignmentFlag.AlignCenter, label)


def mark_rect(rect, white_bottom, mark):
    cell = rect.width() / 8
    square = mark["square"]
    point = (mark.get("points") or {}).get(square)
    if point:
        x = rect.x() + point[0] * rect.width() - cell / 2
        y = rect.y() + point[1] * rect.height() - cell / 2
    else:
        row, col = square_to_cell(square, white_bottom)
        x, y = rect.x() + col * cell, rect.y() + row * cell
    return QRectF(x, y, cell, cell)


def paint_marks(painter, rect, white_bottom, marks):
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    for mark in marks:
        kind = mark["kind"]
        if kind == "gain_arrow":
            continue
        square = mark_rect(rect, white_bottom, mark)
        cell = square.width()
        color = QColor(mark["color"])
        if kind != "attack":
            wash = QColor(color)
            wash.setAlpha(44 if kind == "mate" else 32)
            painter.fillRect(square, wash)
        radius = max(2.2, cell * (.048 if kind == "attack" else .068))
        center = square.bottomRight() - QPointF(cell * .13, cell * .13)
        painter.setPen(QPen(QColor("#21192d"), max(.8, cell * .015)))
        painter.setBrush(color)
        if kind == "mate":
            painter.drawPolygon(QPolygonF([center + offset for offset in (
                QPointF(0, -radius), QPointF(radius, 0), QPointF(0, radius), QPointF(-radius, 0)
            )]))
        else:
            painter.drawEllipse(center, radius, radius)
    painter.restore()


def paint_gain_arrows(painter, rect, white_bottom, marks):
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    badges = []
    for mark in marks:
        if mark["kind"] != "gain_arrow":
            continue
        move = chess.Move.from_uci(mark["move"])
        target = mark_rect(rect, white_bottom, mark)
        origin = mark_rect(rect, white_bottom, dict(mark, square=move.from_square))
        cell = target.width()
        start, end = origin.center(), target.center()
        delta = end - start
        length = math.hypot(delta.x(), delta.y())
        if not length:
            continue
        unit = delta / length
        perpendicular = QPointF(-unit.y(), unit.x())
        point = end - unit * cell * .11
        stem = start + unit * cell * .18
        tail = point - unit * cell * .21
        half_head = perpendicular * cell * .125
        shape = QPainterPath(stem)
        shape.lineTo(tail)
        shape.moveTo(tail + half_head)
        shape.lineTo(point)
        shape.lineTo(tail - half_head)

        color = QColor(mark["color"])
        stroke = max(1.6, cell * .032)
        border = QColor("#1a1527")
        for ink, width in ((border, stroke + 2.4), (color, stroke)):
            painter.setPen(QPen(ink, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(shape)
        badges.append((stem + (point - stem) * .56, cell, mark["label"], color, border))

    for center, cell, label, color, border in badges:
        font = QFont("Arial")
        font.setBold(True)
        font.setPixelSize(max(9, min(17, round(cell * .19))))
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        width = metrics.horizontalAdvance(label) + max(12, cell * .27)
        height = max(13, metrics.height() + 3)
        badge = QRectF(center.x() - width / 2, center.y() - height / 2, width, height)
        painter.setPen(QPen(color, max(1, cell * .02)))
        painter.setBrush(border)
        painter.drawRoundedRect(badge, height * .31, height * .31)
        painter.setPen(QColor("#f8f4ff"))
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, label)
    painter.restore()


class BoardOverlay(QWidget):
    is_board_overlay = True

    def __init__(self):
        flags=(Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|
               Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.WindowTransparentForInput|
               Qt.WindowType.WindowDoesNotAcceptFocus|Qt.WindowType.NoDropShadowWindowHint)
        super().__init__(None,flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: none;")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.arrows=[]
        self.marks=[]
        self.overlap_color = DEFAULT_OVERLAP_COLOR
        self.white_bottom=True
        self._native_panel=None
        self._native_mac=(sys.platform=='darwin' and not os.environ.get('BOARDLENS_TEST_MODE')
                          and os.environ.get('QT_QPA_PLATFORM')!='offscreen')
        self._windows_configured=False
        self.capture_excluded=False

    def _mac_panel(self):
        if self._native_panel is None:
            from .mac_overlay import PassivePanel
            self._native_panel=PassivePanel()
        return self._native_panel

    def capture_window_id(self):
        if self._native_mac:
            return int(self._mac_panel().panel.windowNumber())
        return 0

    def isVisible(self):
        if self._native_mac:
            return bool(self._native_panel and self._native_panel.panel.isVisible())
        return super().isVisible()

    def hide(self):
        if self._native_panel:
            self._native_panel.hide()
        super().hide()

    def close(self):
        if self._native_panel:
            self._native_panel.close()
            self._native_panel=None
        return super().close()

    def _configure_windows(self):
        if sys.platform!='win32' or self._windows_configured:
            return
        import ctypes
        from ctypes import wintypes
        api=ctypes.windll.user32
        api.GetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int]
        api.GetWindowLongPtrW.restype=ctypes.c_ssize_t
        api.SetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_ssize_t]
        api.SetWindowLongPtrW.restype=ctypes.c_ssize_t
        hwnd=int(self.winId())
        style=api.GetWindowLongPtrW(hwnd,-20)
        # Native layered-window hit testing and no activation, across processes.
        api.SetWindowLongPtrW(hwnd,-20,style|0x20|0x80000|0x08000000|0x80)
        api.SetWindowDisplayAffinity.argtypes=[wintypes.HWND,wintypes.DWORD]
        self.capture_excluded=bool(api.SetWindowDisplayAffinity(hwnd,0x11))
        self._windows_configured=True

    def set_arrows(self, geometry, white_bottom, arrows, screen=None, marks=None):
        self.white_bottom=white_bottom
        self.arrows=arrows
        self.marks=marks or []
        if self._native_mac:
            self.setGeometry(geometry)
            if arrows or self.marks:
                from PySide6.QtGui import QGuiApplication
                primary=QGuiApplication.primaryScreen()
                self._mac_panel().update(geometry,screen.devicePixelRatio() if screen else 1,
                                         white_bottom,arrows,primary.geometry().height(),self.marks,
                                         self.overlap_color)
            else:
                self.hide()
            return
        self._configure_windows()
        if screen is not None:
            self.winId()
            if self.windowHandle().screen() != screen:
                self.windowHandle().setScreen(screen)
        self.setGeometry(geometry)
        self.update()
        if arrows or self.marks:
            if not super().isVisible():
                self.show()
        else:
            self.hide()

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(),Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        paint_marks(painter,QRectF(self.rect()),self.white_bottom,self.marks)
        paint_arrows(painter, QRectF(self.rect()), self.white_bottom, self.arrows, self.overlap_color)
        paint_gain_arrows(painter, QRectF(self.rect()), self.white_bottom, self.marks)
