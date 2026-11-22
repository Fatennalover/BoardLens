"""Appearance helpers for the native BoardLens layout."""
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QPushButton


class ArrowColorButton(QPushButton):
    color_changed = Signal(str)

    def __init__(self, color, label):
        super().__init__()
        self.setAccessibleName(label)
        self.setToolTip("Open the color picker")
        self.set_color(QColor(color))
        self.clicked.connect(self.choose)

    def set_color(self, color):
        self.color = color.name()
        ink = "#15151c" if color.lightness() > 145 else "#ffffff"
        self.setText("Choose color")
        self.setStyleSheet(f"background:{self.color};color:{ink};")

    def choose(self):
        color = QColorDialog.getColor(QColor(self.color), self, self.accessibleName())
        if color.isValid() and color.name() != self.color:
            self.set_color(color)
            self.color_changed.emit(self.color)


WORKSPACE_STYLE = """
QMainWindow, QDialog, QWidget { background:#12111c; color:#f1eef9; font-size:16px; }
QWidget#boardPanel, QWidget#analysisPanel, QWidget#workspaceToolbar {
    background:#1a1828; border:1px solid #322b47; border-radius:12px;
}
QWidget#analysisOptionsBar {
    background:#171425; border:1px solid #322b47; border-radius:10px;
}
QWidget#analysisOptionsBar QPushButton { padding:5px 8px; min-height:20px; }
QWidget#browserSetupStep {
    background:#1a1828; border:1px solid #403656; border-radius:10px;
}
QWidget#browserSetupStep QLabel { background:transparent; }
QLabel#browserSetupHeading { font-weight:700; color:#d5c2ff; }
QWidget#boardPanel QLabel, QWidget#analysisPanel QLabel { background:transparent; }
QLabel#workspaceTitle { font-size:24px; font-weight:700; }
QLabel#status { color:#c6bed9; font-size:13px; background:#1a1828; padding:9px 12px; }
QPushButton, QToolButton {
    color:#f4efff; background:#242036; border:1px solid #403656; border-radius:8px;
    padding:8px 13px; min-height:20px;
}
QPushButton:hover, QToolButton:hover { background:#302549; border-color:#9172c7; }
QPushButton:checked, QToolButton:checked { color:#f7efff; background:#483168; border-color:#9e79da; }
QPushButton#primary { background:#c9b1ff; color:#211338; border-color:#c9b1ff; }
QPushButton#stop { background:#412734; color:#f7dbe3; border-color:#794556; }
QPushButton:disabled { color:#918aa7; background:#242031; border-color:#352e45; }
QPushButton[toggle="true"] { background:#272137; border:1px solid #43365a; }
QPushButton[toggle="true"]:checked { background:#c7affb; color:#24173a; border-color:#d5c2ff; }
QPushButton[toggle="true"]:hover { border-color:#b79be8; }
QTabBar::tab { color:#c6bed9; background:#1a1828; padding:9px 16px; }
QTabWidget#boardAnalysisTabs QTabBar::tab { padding:9px 7px; }
QTabBar::tab:selected { color:#eee3ff; background:#2d2244; border-bottom:2px solid #b991f5; }
QTextBrowser, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    color:#f2edf9; background:#211c30; border:1px solid #403656; border-radius:7px;
    selection-background-color:#61478b;
}
QTextBrowser#analysisDocument { background:#1a1828; border:0; padding:8px 3px; }
QGroupBox { border:1px solid #403656; border-radius:10px; margin-top:12px; }
QGroupBox::title {
    subcontrol-origin:margin; subcontrol-position:top left; left:9px;
    padding:0 5px; background:#15131f; color:#ded2f5; font-size:15px;
}
QSplitter::handle { background:#15131f; width:12px; }
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background:#35294a;
}
"""

WORKSPACE_STYLE += """
QPushButton:focus, QToolButton:focus, QLineEdit:focus, QComboBox:focus {
    border-color:#b79be8;
}
QScrollArea, QTabWidget::pane { border:0; }
QListWidget, QTableWidget {
    color:#f1eef9; background:#1a1828; border:1px solid #403656;
    border-radius:8px; selection-background-color:#493465; selection-color:#f5edff;
}
QListWidget::item { padding:9px; border-bottom:1px solid #2c263e; }
QListWidget::item:selected, QMenu::item:selected { color:#f5edff; background:#493465; }
QHeaderView::section { padding:8px; border:0; background:#312346; color:#f0e5fc; }
QTableWidget { gridline-color:#3b3050; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { padding:5px 8px; min-height:22px; }
QSpinBox, QDoubleSpinBox, QComboBox { padding-right:32px; }
QComboBox::drop-down { border:0; width:24px; }
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin:border; subcontrol-position:top right; width:24px;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin:border; subcontrol-position:bottom right; width:24px;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image:url("UP_ICON"); width:12px; height:8px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow, QComboBox::down-arrow {
    image:url("DOWN_ICON"); width:12px; height:8px;
}
QComboBox QAbstractItemView { selection-background-color:#493465; selection-color:#f5edff; }
QToolTip { color:#f4edff; background:#2b213d; border:1px solid #695187; padding:5px; }
QScrollBar:vertical { width:9px; background:transparent; margin:2px; }
QScrollBar::handle:vertical { background:#65517f; border-radius:3px; min-height:28px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical { background:transparent; }
QMenu { background:#231b33; border:1px solid #4f3d66; padding:5px; }
QMenu::item { padding:9px 22px 9px 12px; }
"""
for name in ("up", "down"):
    path = Path(__file__).parent / "assets" / "ui" / f"{name}.svg"
    WORKSPACE_STYLE = WORKSPACE_STYLE.replace(f"{name.upper()}_ICON", path.as_posix())
