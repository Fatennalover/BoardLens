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
COACH_PREVIEW_COLOR = "#eab1ff"
COACH_REPLY_COLOR = "#76e3dc"


def shafts_share_segment(first, second, cell):
    start, end = first
    axis = end - start
    length = math.hypot(axis.x(), axis.y())
    if length == 0:
        return False
    unit = axis / length
    a, b = (point - start for point in second)
    distance = max(abs(point.x() * unit.y() - point.y() * unit.x()) for point in (a, b))
    if distance > cell * .015:
        return False
    low, high = sorted(point.x() * unit.x() + point.y() * unit.y() for point in (a, b))
    return min(length, high) - max(0., low) > cell * .16


def paint_arrows(painter, rect, white_bottom, arrows, overlap_color=DEFAULT_OVERLAP_COLOR):
    if not arrows or rect.isEmpty():
        return
    cell = rect.width() / 8
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    shapes = []
    labels = []
    previews = []
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
        preview = arrow.get("preview")
        pen = QPen(color, max(3, cell * (.135 if preview else .095)), style, Qt.PenCapStyle.RoundCap)
        shaft = QPainterPath(start)
        dx, dy = abs(end.x() - start.x()) / cell, abs(end.y() - start.y()) / cell
        tail = start
        if not projected and (round(dx), round(dy)) in ((1, 2), (2, 1)):
            tail = QPointF(end.x(), start.y()) if dx > dy else QPointF(start.x(), end.y())
            shaft.lineTo(tail)
            shaft.moveTo(tail)
        shaft.lineTo(end)

        angle = math.atan2(end.y() - tail.y(), end.x() - tail.x())
        length = cell * (.36 if preview else .29)
        head = QPainterPath()
        head.addPolygon(QPolygonF([end,
            QPointF(end.x() - length * math.cos(angle - .52), end.y() - length * math.sin(angle - .52)),
            QPointF(end.x() - length * math.cos(angle + .52), end.y() - length * math.sin(angle + .52))]))
        head.closeSubpath()
        shape = QPainterPathStroker(pen).createStroke(shaft).united(head)
        if preview:
            previews.append((shape, color))
            continue
        painter.fillPath(shape, color)
        bounds = shape.boundingRect()
        segments = [(start, tail), (tail, end)] if tail != start else [(start, end)]
        for other, other_bounds, other_segments in shapes:
            if bounds.intersects(other_bounds) and any(
                    shafts_share_segment(segment, previous, cell)
                    for segment in segments for previous in other_segments):
                overlaps = overlaps.united(shape.intersected(other))
        shapes.append((shape, bounds, segments))

        if arrow.get("label"):
            labels.append((arrow["label"], start * .28 + end * .72, color))

    painter.fillPath(overlaps, QColor(overlap_color))
    if labels:
        font = QFont("Arial", max(8, round(cell * .12)), QFont.Weight.Bold)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        for label, center, color in labels:
            width, height = metrics.horizontalAdvance(label) + 8, metrics.height() + 3
            box = QRectF(center.x() - width / 2, center.y() - height / 2, width, height)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#152630"))
            painter.drawRoundedRect(box, 2, 2)
            painter.setPen(color.lighter(130))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, label)
    for shape, color in previews:
        painter.strokePath(shape, QPen(QColor("#2c173f"), max(2, cell * .055),
                                       Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.fillPath(shape, color)


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


def score_arrow_points(start, end, cell):
    delta = end - start
    unit = delta / math.hypot(delta.x(), delta.y())
    perpendicular = QPointF(-unit.y(), unit.x())
    stem = start + unit * cell * .16
    tip = end - unit * cell * .10
    tail = tip - unit * cell * .27
    wing = perpendicular * cell * .15
    chevron = [tip, tail + wing, tail + unit * cell * .08, tail - wing]
    return stem, tail, chevron, start + delta * .64


def score_badge_points(center, width, height):
    x, y = center.x() - width / 2, center.y() - height / 2
    notch = height * .25
    return [QPointF(x, y), QPointF(x + width, y),
            QPointF(x + width + notch, center.y()), QPointF(x + width, y + height),
            QPointF(x, y + height), QPointF(x - notch, center.y())]


def space_score_badge(center, delta, width, height, occupied, board_rect):
    side = QPointF(-delta.y(), delta.x()) / math.hypot(delta.x(), delta.y()) * height
    for offset in (QPointF(), side * .8, side * -.8, side * 1.4, side * -1.4):
        for shift in (0., -.20, .14, -.37):
            point = center + delta * shift + offset
            bounds = QRectF(point.x() - width / 2 - height * .25 - 1,
                            point.y() - height / 2 - 1, width + height * .5 + 2, height + 2)
            if board_rect.contains(bounds) and not any(bounds.intersects(other) for other in occupied):
                occupied.append(bounds)
                return point
    return center


def paint_gain_arrows(painter, rect, white_bottom, marks):
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    badges = []
    dark = QColor("#14121e")
    for mark in marks:
        if mark["kind"] != "gain_arrow":
            continue
        move = chess.Move.from_uci(mark["move"])
        target = mark_rect(rect, white_bottom, mark)
        origin = mark_rect(rect, white_bottom, dict(mark, square=move.from_square))
        cell = target.width()
        if target.center() == origin.center():
            continue
        stem, tail, head, center = score_arrow_points(origin.center(), target.center(), cell)
        color = QColor(mark["color"])
        width = max(2., cell * .044)
        for ink, stroke in ((dark, width + 2.4), (color, width)):
            pen = QPen(ink, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap)
            pen.setDashPattern([cell * .115 / stroke, cell * .090 / stroke])
            painter.setPen(pen)
            painter.drawLine(stem, tail)
        painter.setBrush(dark)
        painter.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPolygon(QPolygonF(head))
        badges.append((center, target.center() - origin.center(), cell, mark["label"], color))

    occupied = []
    for center, delta, cell, label, color in badges:
        font = QFont("Arial")
        font.setBold(True)
        font.setPixelSize(max(11, min(22, round(cell * .23))))
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        width = metrics.horizontalAdvance(label) + max(13, cell * .22)
        height = max(16, metrics.height() + 4)
        center = space_score_badge(center, delta, width, height, occupied, rect)
        painter.setPen(QPen(color, max(1.3, cell * .025)))
        painter.setBrush(dark)
        painter.drawPolygon(QPolygonF(score_badge_points(center, width, height)))
        painter.setPen(QColor("#ffffff"))
        box = QRectF(center.x() - width / 2, center.y() - height / 2, width, height)
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, label)
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
