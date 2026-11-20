"""Shared app icon and scalable BoardLens branding."""
from pathlib import Path
import sys

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QWidget

ASSETS = Path(__file__).parent / 'assets/ui'


def app_icon():
    mac = ASSETS / 'boardlens-icon-mac.png'
    return QIcon(str(mac if sys.platform == 'darwin' and mac.exists() else ASSETS / 'boardlens-icon-rounded.png'))


class BrandBanner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logo = QPixmap(str(ASSETS / 'boardlens-icon-rounded.png'))
        self.setAccessibleName('BoardLens')
        self.set_compact(False)

    def set_compact(self, compact):
        self.compact = compact
        self.setFixedHeight(50 if compact else 100)
        self.update()

    def paintEvent(self, event):
        r = QRectF(self.rect())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        clip = QPainterPath()
        clip.addRoundedRect(r, 12, 12)
        painter.setClipPath(clip)
        background = QLinearGradient(0, r.height(), r.width(), 0)
        background.setColorAt(0, QColor('#221447'))
        background.setColorAt(.55, QColor('#100c22'))
        background.setColorAt(1, QColor('#31155a'))
        painter.fillRect(r, background)
        ribbon = QPainterPath()
        ribbon.moveTo(r.width() * .58, r.height())
        ribbon.cubicTo(r.width() * .77, r.height() * .76, r.width() * .84, 0, r.width(), 0)
        ribbon.lineTo(r.width(), r.height())
        ribbon.closeSubpath()
        light = QLinearGradient(r.width() * .58, r.height(), r.width(), 0)
        light.setColorAt(0, QColor('#170f31'))
        light.setColorAt(1, QColor('#5628a0'))
        painter.fillPath(ribbon, light)

        icon_size = 30 if self.compact else 62
        left = 14 if self.compact else 28
        painter.drawPixmap(QRectF(left, (r.height()-icon_size)/2, icon_size, icon_size),
                           self.logo, QRectF(self.logo.rect()))
        font = QFont()
        font.setPixelSize(24 if self.compact else 45)
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        text = QRectF(left + icon_size + (10 if self.compact else 16), 0, r.width(), r.height())
        painter.setPen(QColor('#f7f3ff'))
        painter.drawText(text, Qt.AlignmentFlag.AlignVCenter, 'Board')
        text.translate(painter.fontMetrics().horizontalAdvance('Board'), 0)
        painter.setPen(QColor('#be98ff'))
        painter.drawText(text, Qt.AlignmentFlag.AlignVCenter, 'Lens')
