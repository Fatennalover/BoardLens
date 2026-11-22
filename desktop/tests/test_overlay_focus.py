import sys
from types import SimpleNamespace

import chess
import numpy as np

from chess_helper.app import MainWindow, SCREEN_REFRESH_MS
from chess_helper.core import save_settings
from chess_helper.overlay import BoardOverlay


def test_repeated_updates_do_not_show_or_raise_again(qt, monkeypatch):
    from PySide6.QtCore import QRect
    overlay=BoardOverlay()
    shows=[]
    original=overlay.show
    def show():
        shows.append(True)
        original()
    monkeypatch.setattr(overlay,'show',show)
    monkeypatch.setattr(overlay,'raise_',lambda: (_ for _ in ()).throw(AssertionError('raised')))
    arrows=[{'move':chess.Move.from_uci('e2e4'),'color':'#ffc65c'}]
    for _ in range(20):
        overlay.set_arrows(QRect(0,0,400,400),True,arrows)
    assert len(shows)==1
    overlay.close()


def test_refresh_is_hardcoded_and_engine_time_is_preserved(qt):
    save_settings({'seconds':4.5,'depth':24,'interval':450})
    window=MainWindow()
    assert window.timer.interval()==SCREEN_REFRESH_MS==45
    assert window.interval.value()==45
    assert not window.interval.isVisible()
    assert window.seconds.value()==4.5
    assert window.search_settings().seconds==4.5
    window.seconds.setValue(.7)
    assert window.search_settings().seconds==.7
    assert not window.always_top.isChecked()
    window.close()


def test_quick_arrows_toggle_does_not_stop_monitoring_or_search(qt):
    window=MainWindow()
    window._monitoring=True
    window.live_button.setChecked(True)
    generation=window.generation
    job=SimpleNamespace(cancel=lambda:None)
    window.job=job
    window.quick_arrows.click()
    assert not window.overlay_enabled.isChecked()
    assert window._monitoring and window.live_button.isChecked()
    assert window.generation==generation and window.job is job
    window.dispatch('arrows')
    assert window.overlay_enabled.isChecked()
    assert window._monitoring and window.generation==generation
    window.close()


def test_native_image_provider_allocation_padding_is_ignored(monkeypatch):
    from chess_helper.mac_capture import _bgr
    row1=bytes([1,2,3,255,4,5,6,255,0,0,0,0])
    row2=bytes([7,8,9,255,10,11,12,255,0,0,0,0])
    data=row1+row2+b'paddingpastimage'
    api=SimpleNamespace(CGImageGetWidth=lambda _:2,CGImageGetHeight=lambda _:2,
        CGImageGetBytesPerRow=lambda _:12,CGImageGetBitmapInfo=lambda _:8194,
        CGImageGetBitsPerPixel=lambda _:32,CGImageGetDataProvider=lambda _:None,
        CGDataProviderCopyData=lambda _:data,kCGBitmapByteOrderMask=0x7000,
        kCGBitmapByteOrder32Little=0x2000)
    monkeypatch.setitem(sys.modules,'Quartz',api)
    assert np.array_equal(_bgr(None),np.array([[[1,2,3],[4,5,6]],[[7,8,9],[10,11,12]]],np.uint8))


def test_offset_gradient_candidate_does_not_hide_better_component_box(monkeypatch):
    import cv2
    from pathlib import Path
    import chess_helper.detection as detection
    fixture=cv2.imread(str(Path(__file__).parent/'fixtures/chesscom-italian-white.png'))
    canvas=np.full((1000,1500,3),24,np.uint8)
    canvas[200:762,20:920]=cv2.resize(fixture,(900,562))
    extents=iter([[(164,631)],[(241,708)]])
    monkeypatch.setattr(detection,'_extents',lambda _:next(extents))
    candidates=detection.grid_candidates(canvas)
    assert any(d.score>=.95 and abs(d.x-159)<5 and abs(d.size-480)<9 for d in candidates)


def test_browser_covering_helper_does_not_mask_the_browser_board():
    from chess_helper.mac_capture import _visible_helper_masks
    def window(pid,number,x,y,w,h):
        return {'kCGWindowOwnerPID':pid,'kCGWindowNumber':number,'kCGWindowLayer':0,
                'kCGWindowAlpha':1,'kCGWindowBounds':dict(X=x,Y=y,Width=w,Height=h)}
    helper=window(10,100,1000,0,480,900)
    browser=window(20,200,0,0,1512,982)
    assert _visible_helper_masks([browser,helper],10,set())==[]
    assert _visible_helper_masks([helper,browser],10,set())==[(1000.,0.,480.,900.)]


def test_one_file_offset_hint_is_reacquired_instead_of_imported():
    import cv2
    from pathlib import Path
    from chess_helper.recognition import Recognizer,position_from_read
    image=cv2.imread(str(Path(__file__).parent/'fixtures/chesscom-italian-white.png'))
    recognizer=Recognizer()
    result=recognizer.scan(image)
    expected=position_from_read(result)[0].board_fen()
    d=result.detection
    result=recognizer.scan(image,(d.x-round(d.size/8),d.y,d.size))
    assert position_from_read(result)[0].board_fen()==expected


def test_hidden_overlay_is_always_excluded_during_capture_races(qt,monkeypatch):
    from PySide6.QtGui import QGuiApplication
    from chess_helper.capture import BoardRegion,screen_key
    import chess_helper.mac_capture as native_capture
    window=MainWindow()
    screen=QGuiApplication.primaryScreen()
    window.region=BoardRegion(screen_key(screen),800,800,100,100,400)
    window.overlay._native_mac=True
    monkeypatch.setattr(window.overlay,'capture_window_id',lambda:12345)
    monkeypatch.setattr(window.overlay,'isVisible',lambda:False)
    captures=[]
    monkeypatch.setattr(native_capture,'capture_frames',lambda specs,excluded,cancelled:captures.append((specs,excluded)) or [])
    monkeypatch.setattr(window.live_worker,'submit',lambda token,provider,hint:provider(__import__('threading').Event()))
    window._monitoring=True
    window.request_scan()
    assert captures[0][1]=={12345}
    assert captures[0][0][0]['crop']==(100,100,400)
    window.overlay._native_mac=False
    window.close()


def test_only_the_shared_part_of_overlapping_arrows_changes_color(qt):
    import chess
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter
    from chess_helper.overlay import DEFAULT_OVERLAP_COLOR, paint_arrows

    position = chess.Board("7k/2P5/8/8/8/2r5/8/K7 w - - 0 1")
    separate_move = position.parse_uci("a1a2")
    promotion = position.parse_uci("c7c8q")
    position.push(promotion)
    reply = position.parse_uci("c3c8")
    arrows = [
        {"move": promotion, "color": "#ffb454"},
        {"move": reply, "color": "#53e2e4", "reply": True},
        {"move": separate_move, "color": "#e38e13"},
    ]
    for color in (DEFAULT_OVERLAP_COLOR, "#38e67b"):
        image = QImage(800, 800, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        paint_arrows(painter, QRectF(0, 0, 800, 800), True, arrows, color)
        painter.end()

        assert image.pixelColor(250, 100) == QColor(color)
        assert image.pixelColor(250, 300).blue() > image.pixelColor(250, 300).red()
        assert image.pixelColor(50, 700).red() > image.pixelColor(50, 700).blue()
        assert image.pixelColor(400, 300).alpha() == 0


def test_overlap_picker_applies_and_saves_the_color(qt, monkeypatch):
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QColorDialog
    from chess_helper.overlay import DEFAULT_OVERLAP_COLOR

    window = MainWindow()
    try:
        assert window.overlap_arrow_button.color == DEFAULT_OVERLAP_COLOR
        monkeypatch.setattr(QColorDialog, "getColor", lambda *_: QColor("#38e67b"))
        window.overlap_arrow_button.click()
        assert window.board_view.overlap_color == "#38e67b"
        assert window.overlay.overlap_color == "#38e67b"
        assert window.multi.primary_card.view.overlap_color == "#38e67b"
        assert window.autosave_timer.isActive()
    finally:
        window.close()
    restored = MainWindow()
    try:
        assert restored.overlap_arrow_button.color == "#38e67b"
    finally:
        restored.close()


def test_arrows_that_only_meet_at_a_square_do_not_draw_an_overlap_dot(qt):
    import chess
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter
    from chess_helper.overlay import DEFAULT_OVERLAP_COLOR, paint_arrows

    arrows = [
        {"move": chess.Move.from_uci("d2d4"), "color": "#ffb454"},
        {"move": chess.Move.from_uci("c5d4"), "color": "#53e2e4", "reply": True},
    ]
    image = QImage(800, 800, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    paint_arrows(painter, QRectF(0, 0, 800, 800), True, arrows)
    painter.end()
    assert image.pixelColor(350, 450).alpha() > 0
    assert all(image.pixelColor(x, y) != QColor(DEFAULT_OVERLAP_COLOR)
               for x in range(337, 364) for y in range(437, 464))
