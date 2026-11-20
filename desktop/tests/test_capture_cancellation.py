import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from chess_helper import mac_capture
from chess_helper.mac_capture import CaptureCancelled, CaptureUnavailable, _await


def test_capture_wait_is_bounded_and_stop_interrupts_it():
    began=time.monotonic()
    with pytest.raises(RuntimeError):_await(lambda callback:None,threading.Event(),timeout=.04)
    assert time.monotonic()-began<.4
    cancel=threading.Event();timer=threading.Timer(.02,cancel.set);timer.start();began=time.monotonic()
    with pytest.raises(CaptureCancelled):_await(lambda callback:None,cancel,timeout=2)
    assert time.monotonic()-began<.3
    timer.join()


def test_interrupted_display_does_not_block_other_displays(monkeypatch):
    content = SimpleNamespace(windows=lambda: [], displays=lambda: [])
    refreshes = []

    def refresh(_desktop, _onscreen, callback):
        refreshes.append(True)
        callback(content, None)

    shareable_content = SimpleNamespace(
        getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_=refresh)
    api = SimpleNamespace(SCShareableContent=shareable_content)
    attempts = []
    unavailable = {"first"}
    now = [10.]

    def capture(_api, _displays, _excluded, spec, _cancelled):
        key = spec["key"]
        attempts.append(key)
        if key in unavailable:
            raise CaptureUnavailable("Timed out")
        return key

    monkeypatch.setattr(mac_capture, "_cached_content", None)
    monkeypatch.setattr(mac_capture, "_cached_at", 0.)
    monkeypatch.setattr(mac_capture, "_cached_exclusions", set())
    monkeypatch.setattr(mac_capture, "_display_retry_at", {})
    monkeypatch.setattr(mac_capture, "time", SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr(mac_capture, "_capture_display", capture)
    specs = [{"key": "first"}, {"key": "second"}]
    cancel = threading.Event()
    assert mac_capture._capture_displays(api, specs, set(), cancel) == ["second"]
    assert mac_capture._capture_displays(api, specs, set(), cancel) == ["second"]
    assert attempts == ["first", "second", "second"]
    assert len(refreshes) == 2
    unavailable.clear()
    now[0] += 1.
    assert mac_capture._capture_displays(api, specs, set(), cancel) == ["first", "second"]


def test_live_scan_recovers_automatically_after_an_interruption(qt, monkeypatch):
    import cv2
    from PySide6.QtGui import QGuiApplication
    from chess_helper.app import MainWindow
    from chess_helper.capture import BoardRegion, screen_key

    image = cv2.imread(str(Path(__file__).parent / "fixtures/chesscom-starting-layout-nov10.png"))
    height, width = image.shape[:2]
    window = MainWindow()
    window.source.setCurrentIndex(1)
    window.timer.stop()
    screen = QGuiApplication.primaryScreen()
    key = screen_key(screen)
    window.region = BoardRegion(key, width, height, 0, 0, 400)
    window._last_discovery_at = time.monotonic()
    window._force_full_scan = False
    monkeypatch.setattr(window.multi, "regions", lambda: [window.region])
    monkeypatch.setattr(window.overlay, "capture_window_id", lambda: None)
    monkeypatch.setattr(window, "suggest", lambda **_: None)
    attempts = []

    def capture(specs, _excluded, _cancelled):
        crop = specs[0].get("crop")
        attempts.append(crop)
        if len(attempts) == 1:
            raise CaptureUnavailable("Timed out")
        if crop:
            x, y, size = crop
            return [(key, screen.name(), image[y:y+size, x:x+size], (*crop, width, height))]
        return [(key, screen.name(), image)]

    def wait_for(predicate):
        deadline = time.monotonic() + 3.
        while not predicate() and time.monotonic() < deadline:
            qt.processEvents()
            time.sleep(.01)
        assert predicate()

    monkeypatch.setattr(mac_capture, "capture_frames", capture)
    try:
        window.overlay._native_mac = True
        window.request_scan()
        wait_for(lambda: "retrying automatically" in window.status_label.text())
        assert window._monitoring and window.live_button.isChecked()
        window.timer.start(45)
        wait_for(lambda: window._screen_confirmed)
        assert attempts[:2] == [(0, 0, 400), None]
    finally:
        window.overlay._native_mac = False
        window.close()
