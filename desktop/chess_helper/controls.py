from __future__ import annotations

import os
import sys

from PySide6.QtCore import QObject, Signal

from .core import validate_keys


class Hotkeys(QObject):
    action = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.listener = None
        self.native = None

    def start(self, bindings):
        bindings = validate_keys(bindings)
        if sys.platform == 'darwin' and not os.environ.get('BOARDLENS_TEST_MODE'):
            from .mac_hotkeys import NativeHotkeys
            self.native = self.native or NativeHotkeys(self.action.emit)
            self.native.start(bindings)
            return
        from pynput import keyboard
        for combo in bindings.values():
            keyboard.HotKey.parse(combo)
        self.stop()
        if not getattr(keyboard.Listener, "IS_TRUSTED", True):
            raise RuntimeError("Global keys need Accessibility / Input Monitoring permission for your launcher. App buttons still work.")
        self.listener = keyboard.GlobalHotKeys({combo: (lambda action=action: self.action.emit(action))
                                               for action, combo in bindings.items()})
        self.listener.start()

    def stop(self):
        if self.native:
            self.native.stop()
        if self.listener:
            self.listener.stop()
            self.listener = None
