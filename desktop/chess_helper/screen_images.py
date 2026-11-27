"""Local image sources that share the desktop recognition pipeline."""
from concurrent.futures import ThreadPoolExecutor
import os
import sys
from threading import Event

import chess
import cv2
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QInputDialog, QMenu, QMessageBox, QSpinBox)

from .capture import BoardRegion, capture, pixmap_bgr, screen_key
from .core import PositionTracker, ordered_symbols
from .recognition import Recognizer, position_from_read, visible_attacks
from .widgets import CropDialog


class ScreenImages(QObject):
    ready = Signal(int, object, object, str)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='BoardLens-image')
        self.recognizer = Recognizer()
        self.revision = 0
        self.cancelled = Event()
        self.images = []
        self.current = None
        self.frozen = None
        self.ready.connect(self.finished)

    def menu(self, parent):
        menu = QMenu(parent)
        menu.addAction('Open screenshot…', self.open)
        menu.addAction('Capture a display…', self.capture_display)
        if sys.platform in ('darwin','win32'):
            menu.addAction('Capture a window…', self.window_image)
        menu.addAction('Capture a board region…', lambda: self.capture_display(crop=True))
        menu.addAction('Track a board region…', lambda: self.capture_display(crop=True, track=True))
        untrack = menu.addAction('Stop tracking a region…', self.untrack)
        menu.addAction('Inspect a partial board image…', lambda: self.open(partial=True))
        menu.addSeparator()
        choose = menu.addAction('Choose a detected board…', self.choose)
        freeze = menu.addAction('Freeze frame', self.freeze)
        resume = menu.addAction('Resume live screen', self.resume)

        def update():
            window = self.window
            choose.setEnabled(window.source.currentIndex() == 2 and len(self.images) > 1)
            untrack.setEnabled(bool(window.multi.manual_regions))
            freeze.setEnabled(window.source.currentIndex() == 1 and window._screen_confirmed and window._turn_known)
            resume.setEnabled(window.source.currentIndex() == 2 and self.frozen is not None)
        menu.aboutToShow.connect(update)
        return menu

    def open(self, partial=False):
        path, _ = QFileDialog.getOpenFileName(self.window, 'Open board screenshot', '', 'Images (*.png *.jpg *.jpeg *.bmp)')
        if not path:
            return
        image = cv2.imread(path)
        if image is None:
            self.window.status('Could not read that image.')
        elif partial:
            self.inspect(image)
        else:
            self.scan(image)

    def capture_display(self, crop=False, track=False):
        window = self.window
        if hasattr(window, 'permissions') and not window.permissions.ensure_capture():
            return
        screens = QGuiApplication.screens()
        if not screens:
            window.status('No display is available to capture.')
            return
        names = [f'Display {index} · {screen.name()}' for index, screen in enumerate(screens,1)]
        selection = next((i for i, screen in enumerate(screens) if screen_key(screen)==window.monitor.currentData()),0)
        if len(screens) > 1:
            name, ok = QInputDialog.getItem(window, 'Capture a display', 'Display', names, selection, False)
            if not ok:
                return
            selection = names.index(name)
        self.cancel()
        revision = self.revision
        screen = screens[selection]
        hidden = [widget for widget in (window, window.settings_dialog) if widget.isVisible()]
        for widget in hidden:
            widget.hide()
        for overlay in window.multi.overlays():
            overlay.hide()

        def take():
            try:
                image = capture(screen)
            except (RuntimeError, ValueError) as error:
                window.status(str(error))
                return
            finally:
                if not window.closing:
                    for widget in hidden:
                        widget.show()
            if window.closing or revision != self.revision:
                return
            if track:
                selection = self.crop_rectangle(image)
                if selection is None:
                    return
                x,y,size,_ = selection
                key = screen_key(screen)
                window.multi.add_region(BoardRegion(key,image.shape[1],image.shape[0],x,y,size))
                if window.monitor.currentData() not in (None,'*',key):
                    window.monitor.setCurrentIndex(max(0,window.monitor.findData('*')))
                window.source.setCurrentIndex(1)
                if not window._monitoring:
                    window.start_live()
                window._force_full_scan=True
                window.request_scan(force=True)
                return
            if crop:
                image = self.crop(image)
                if image is None:
                    return
            self.scan(image)

        QTimer.singleShot(150, self, take)

    def cancel(self):
        self.revision += 1
        self.cancelled.set()
        self.cancelled = Event()

    def window_image(self):
        window = self.window
        if hasattr(window,'permissions') and not window.permissions.ensure_capture():
            return
        if sys.platform == 'darwin':
            from .mac_capture import visible_windows, capture_window
            windows = visible_windows()
        else:
            windows = windows_on_desktop()
        if not windows:
            window.status('No eligible windows are available.')
            return
        names = [f'{idx} · {app} · {title}' for idx, (_,app,title) in enumerate(windows,1)]
        choice, ok = QInputDialog.getItem(window,'Capture a window','Window',names,0,False)
        if not ok:
            return
        window_id = windows[names.index(choice)][0]
        if sys.platform == 'darwin':
            self.scan(lambda cancelled:capture_window(window_id,cancelled))
        else:
            pixmap = QGuiApplication.primaryScreen().grabWindow(window_id)
            if pixmap.isNull():
                window.status('That window is no longer available.')
            else:
                self.scan(pixmap_bgr(pixmap))

    def scan(self, source, partial=None):
        self.cancel()
        ticket, cancelled = self.revision, self.cancelled
        quality = self.window.screen_settings.quality()
        self.window.status('Reading the screenshot…')

        def work():
            if cancelled.is_set():
                return
            image = None
            try:
                image = source(cancelled) if callable(source) else source
                self.recognizer.quality = quality
                found = (self.recognizer.read_visible_squares(image, *partial) if partial
                         else self.recognizer.scan_all(image, cancelled))
                error = ''
            except Exception as exc:
                found, error = None, str(exc)
            if not cancelled.is_set():
                self.ready.emit(ticket, found, image, error)

        self.worker.submit(work)

    def crop(self, image, rectangular=False):
        selection = self.crop_rectangle(image,rectangular)
        if selection is None:
            return None
        x,y,width,height = selection
        return image[y:y+height,x:x+width].copy()

    def crop_rectangle(self, image, rectangular=False):
        dialog = CropDialog(image, parent=self.window, rectangular=rectangular)
        if not dialog.exec():
            return None
        return dialog.canvas.selection

    def untrack(self):
        regions = self.window.multi.manual_regions
        labels = [f'Region {i} · {r.size}px at {r.x}, {r.y}' for i,r in enumerate(regions,1)]
        if not labels:
            return
        label,ok = QInputDialog.getItem(self.window,'Stop tracking a region','Region',labels,0,False)
        if ok:
            self.window.multi.remove_region(regions[labels.index(label)])

    def inspect(self, image):
        image = self.crop(image, rectangular=True)
        if image is None:
            return
        dialog = QDialog(self.window)
        dialog.setWindowTitle('Locate the visible squares')
        form = QFormLayout(dialog)
        square = QComboBox()
        square.addItems(chess.SQUARE_NAMES)
        square.setCurrentText('a8')
        orientation = QComboBox()
        orientation.addItems(['White at bottom', 'Black at bottom'])
        columns, rows = QSpinBox(), QSpinBox()
        for field in (columns, rows):
            field.setRange(1, 8)
            field.setValue(4)
        for label, field in (('Top-left square',square),('Orientation',orientation),('Files visible',columns),('Ranks visible',rows)):
            form.addRow(label,field)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec():
            self.scan(image, (chess.parse_square(square.currentText()), columns.value(), rows.value(), orientation.currentIndex()==0))

    def finished(self, ticket, found, image, error):
        if ticket != self.revision or self.window.closing:
            return
        if error:
            self.window.status(error)
        elif isinstance(found, dict):
            pieces = []
            for square,(symbol,confidence) in found.items():
                name = 'uncertain' if symbol is None else 'empty' if symbol=='.' else (
                    ('White ' if symbol.isupper() else 'Black ') + chess.piece_name(chess.PIECE_SYMBOLS.index(symbol.lower())))
                pieces.append(f'{chess.square_name(square)} · {name} ({confidence:.0%})')
            attacks = visible_attacks(found)
            if attacks:
                arrows = ', '.join(f'{chess.square_name(a)} → {chess.square_name(b)}' for a,b in attacks)
                pieces.append(f'\nVisible attacks · {arrows}')
            QMessageBox.information(self.window, 'Visible squares', '\n'.join(pieces) +
                                    '\n\nOther squares are unknown. Engine analysis requires a complete position.')
            self.window.status('Partial board inspected.')
        elif not found:
            answer = QMessageBox.question(self.window, 'No complete board found',
                                          'Crop the image to the 64 squares and try again?')
            if answer == QMessageBox.StandardButton.Yes and (crop := self.crop(image)) is not None:
                self.scan(crop)
            else:
                self.window.status('No complete supported chessboard found.')
        else:
            self.frozen = None
            self.images, self.current = [(read, None) for read in found], None
            self.choose()

    def choose(self):
        window = self.window
        index = 0
        if len(self.images) > 1:
            labels = [f'Board {i} · {read.detection.size}px at {read.detection.x}, {read.detection.y}'
                      for i, (read, _) in enumerate(self.images, 1)]
            label, ok = QInputDialog.getItem(window, 'Choose a detected board', 'Board', labels, self.current or 0, False)
            if not ok:
                return
            index = labels.index(label)
        if self.current == index:
            return
        if self.current is not None and window.source.currentIndex()==2:
            read, _ = self.images[self.current]
            self.images[self.current] = (read, window.tracker.board.copy())
        read, board = self.images[index]
        if board is None:
            board, known = position_from_read(read)
            if not known:
                turn, ok = QInputDialog.getItem(window, 'Confirm the turn', 'Side to move', ['White','Black'],
                                                int(not board.turn), False)
                if not ok:
                    return
                try:
                    board, _ = position_from_read(read, turn=='White')
                except ValueError as error:
                    window.status(str(error))
                    return
        self.current = index
        self.install(read.image, board, read.white_bottom)

    def freeze(self):
        window = self.window
        read = window._last_read
        if not window._screen_confirmed or not window._turn_known or read is None:
            window.status('Confirm a board and turn before freezing the frame.')
            return
        board = window.tracker.board.copy()
        if read.symbols != ordered_symbols(board,window.white_bottom):
            window.status('Waiting to confirm the current frame.')
            return
        self.frozen = (window.region, read, board, window.white_bottom)
        self.images, self.current = [], None
        self.install(read.image, board, window.white_bottom)
        window.status('Frame frozen. Use Capture → Resume live screen to continue scanning.')

    def install(self, image, board, white_bottom):
        window = self.window
        window.snapshot = image.copy()
        window._screenshot_position = board.copy(), white_bottom
        if window.source.currentIndex() != 2:
            window.source.setCurrentIndex(2)
        else:
            window._white_bottom = white_bottom
            window.set_position(board)
        window.preview(window.snapshot)
        window.live_button.setChecked(True)
        window.suggest()

    def resume(self):
        if self.frozen is None:
            return
        window = self.window
        region, read, board, bottom = self.frozen
        self.frozen = None
        window.source.setCurrentIndex(1)
        window.region, window._last_read = region, read
        window.tracker = PositionTracker(board)
        window._white_bottom = bottom
        window._position_locked = window._turn_known = True
        window.request_scan(force=True)

    def close(self):
        self.cancel()
        self.worker.shutdown(wait=False, cancel_futures=True)


def windows_on_desktop():
    import ctypes
    from ctypes import wintypes
    api = ctypes.windll.user32
    enum_fn = ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    windows = []
    api.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    api.GetWindowThreadProcessId.argtypes = (wintypes.HWND,ctypes.POINTER(wintypes.DWORD))
    api.IsWindowVisible.argtypes = api.IsIconic.argtypes = (wintypes.HWND,)
    api.GetWindowTextW.argtypes = (wintypes.HWND,wintypes.LPWSTR,ctypes.c_int)
    api.EnumWindows.argtypes = (enum_fn,wintypes.LPARAM)

    @enum_fn
    def collect(handle, _):
        pid = wintypes.DWORD()
        api.GetWindowThreadProcessId(handle,ctypes.byref(pid))
        length = api.GetWindowTextLengthW(handle)
        if length > 0 and pid.value != os.getpid() and api.IsWindowVisible(handle) and not api.IsIconic(handle):
            title = ctypes.create_unicode_buffer(length+1)
            api.GetWindowTextW(handle,title,length+1)
            windows.append((handle,'Window',title.value))
        return True

    api.EnumWindows(collect,0)
    return windows
