import time
from pathlib import Path
import chess
import cv2
import pytest
from chess_helper.app import MainWindow
from chess_helper.direct_boards import BrowserReader, exact_read
from chess_helper.live import LiveWorker
from chess_helper.capture import BoardRegion,screen_key
from PySide6.QtGui import QGuiApplication


def wait(qt, condition):
    end=time.monotonic()+5
    while not condition() and time.monotonic()<end:
        qt.processEvents();time.sleep(.01)
    assert condition()


def reader_factory(monkeypatch):
    monkeypatch.setattr('chess_helper.direct_boards.BrowserReader',lambda:BrowserReader(port=0))


def test_reader_choice_is_visible_saved_and_does_not_start_stopped_scanning(qt,monkeypatch):
    reader_factory(monkeypatch);w=MainWindow();w.show();w.open_settings()
    try:
        w.source.blockSignals(True);w.source.setCurrentIndex(1);w.source.blockSignals(False);w.source_controls()
        w.readers_toggle.setChecked(False);qt.processEvents()
        assert w.browser_reader_button.isVisible()
        assert not w._monitoring
        w.browser_reader_button.setChecked(True)
        assert w.browser_reader and not w._monitoring
        assert w.readers_toggle.isChecked()
        assert 'fallback' in w.connection_hint.text()
        w.save(quiet=True);w.restore();assert w.browser_reader_button.isChecked()
        w.browser_reader_button.setChecked(False)
        assert not w.browser_reader and not w._monitoring
        w.save(quiet=True);w.restore();assert not w.browser_reader_button.isChecked()
        assert w.connection_hint.text()=='Screen scan · no extension needed'
    finally:w.close()


def test_switching_readers_releases_old_observations_and_browser_lock(qt,monkeypatch):
    reader_factory(monkeypatch);w=MainWindow()
    try:
        w.source.blockSignals(True);w.source.setCurrentIndex(1);w.source.blockSignals(False)
        w.native_reader_button.setChecked(True)
        w.browser_reader_button.setChecked(True);w.update_foreground('browser')
        w.browser_reader.accept({'source':'qa','boards':[{'fen':chess.STARTING_FEN,'white_bottom':True}]})
        w._last_read=exact_read(chess.STARTING_FEN,True,'browser:qa:0');w._screen_confirmed=True
        w.region=BoardRegion(screen_key(QGuiApplication.primaryScreen()),0,0,256,256,256)
        w.lock_target.setChecked(True);assert w.target_lock.active
        old=w.browser_reader;old.publish({'browser:qa:0':{'arrows':[]}})
        token=w._live_token;w._scan_busy=True
        w.browser_reader_button.setChecked(False)
        assert old.hints=={} and not w.target_lock.active and not w.lock_target.isChecked()
        assert w._live_token>token and not w._scan_busy and w._force_full_scan
        assert w.region is None and w._last_read is None and not w._screen_confirmed
        assert w.native_reader_button.isChecked() and not w._monitoring
        assert w.direct_reads()==[]
    finally:w.close()


def test_extension_has_priority_for_2d_and_no_extension_uses_capture(qt,monkeypatch):
    reader_factory(monkeypatch);w=MainWindow();worker=LiveWorker();results=[];captures=[]
    worker.signals.completed.connect(lambda token,reads,error:results.append((token,reads,error)))
    worker.provider=w.direct_reads
    try:
        w.browser_reader_button.setChecked(True);w.update_foreground('browser')
        w.browser_reader.accept({'source':'2d','boards':[{'fen':chess.STARTING_FEN,'white_bottom':True}]})
        def capture(cancelled):captures.append(True);return []
        worker.submit(1,capture);wait(qt,lambda:len(results)==1)
        assert not captures and results[0][1][0][0]=='browser:2d:0'
        # A temporary connection failure also resumes capture without a restart.
        w.browser_reader.accept({'source':'2d','focused':True,'boards':[]})
        worker.submit(2,capture);wait(qt,lambda:len(results)==2)
        assert len(captures)==1 and not results[-1][2]
        w.browser_reader_button.setChecked(False)
        worker.submit(3,capture);wait(qt,lambda:len(results)==3)
        assert len(captures)==2 and not results[-1][2]
    finally:worker.close();w.close()


def test_browser_frames_isolate_bad_entries_and_prioritize_focused_boards(monkeypatch):
    clock = [10.0]
    monkeypatch.setattr('chess_helper.direct_boards.time.monotonic',lambda:clock[0])
    reader=BrowserReader(port=0)
    try:
        item={'fen':chess.STARTING_FEN,'white_bottom':True,'practice_id':'a'*32,
              'index':1,'practice_focused':True,'exact':True}
        frames=reader.accept({'source':'focus','boards':[{'fen':'invalid'},item]})
        assert len(frames)==1
        clock[0]+=.4
        for index in range(4):
            reader.accept({'source':f'tab-{index}','boards':[{**item,'practice_focused':False}]})
        assert reader.reads()[0][0]=='browser:focus:1'
        assert reader.reads()[0][2].received_at==10.0
        clock[0]+=.15
        assert all(source!='browser:focus:1' for source, *_ in reader.reads())
    finally:
        reader.close()


def test_browser_history_rebuilds_moves_after_joining_in_the_middle(qt, monkeypatch):
    reader=BrowserReader(port=0)
    window=MainWindow()
    try:
        window.source.blockSignals(True)
        window.source.setCurrentIndex(1)
        window.source.blockSignals(False)
        window._monitoring=True
        monkeypatch.setattr(window,'suggest',lambda **kwargs:None)
        window.load_opening_index()
        board=chess.Board()
        moves=['e4','e5','Nf3','Nc6','Bb5','a6']
        for move in moves:
            board.push_san(move)
        item={'fen':board.fen(),'white_bottom':True,'exact':True,'moves':moves,'board_id':'a'*32}
        frames=reader.accept({'source':'office','boards':[item]})
        window.live_finished(window._live_token,frames,'')
        window.analysis_tabs.setCurrentIndex(1)
        assert window.tracker.board.move_stack==board.move_stack
        assert 'Ruy Lopez' in window.moves_opening.text()
        assert '3. Bb5    a6' in window.moves_log.toPlainText()
        assert window.phone.snapshot()['boards'][0]['played_moves']==window.moves_log.toPlainText()
        mismatched=reader.accept({'source':'office','boards':[{**item,'moves':['d4']}]})
        assert getattr(mismatched[0][2],'move_history',None) is None
    finally:
        window.close()
        reader.close()


def test_dashboard_avoids_falling_back_to_pixel_recognition(qt,monkeypatch):
    reader_factory(monkeypatch)
    window=MainWindow()
    worker=LiveWorker()
    consumed=[]
    try:
        window.browser_reader_button.setChecked(True)
        window.update_foreground('browser')
        window.browser_reader.accept({'source':'tab','focused':True,'dashboard':True,'boards':[]})
        worker.provider=window.direct_reads
        worker.signals.completed.connect(lambda token,answer,error:consumed.append((answer,error)))
        worker.submit(1,lambda *_: (_ for _ in ()).throw(AssertionError("pixel fallback ran")))
        wait(qt,lambda:len(consumed)==1)
        assert consumed==[((),"")]
    finally:
        worker.close()
        window.close()


def test_focused_empty_or_malformed_tab_drops_stale_reader_frames():
    reader = BrowserReader(port=0)
    try:
        valid = {'fen':chess.STARTING_FEN,'white_bottom':True}
        reader.accept({'source':'previous','focused':True,'boards':[valid]})
        assert reader.reads()[0][0]=='browser:previous:0'
        reader.accept({'source':'puzzle','focused':True,'boards':[]})
        reader.accept({'source':'previous','focused':False,'boards':[valid]})
        assert not reader.reads() and not reader.suppress_screen_fallback()

        reader.accept({'source':'home','focused':True,'dashboard':True,'boards':[]})
        assert reader.suppress_screen_fallback()
        reader.accept({'source':'home','focused':False,'dashboard':True,'boards':[]})
        assert not reader.suppress_screen_fallback()

        reader.accept({'source':'puzzle','focused':True,'boards':[valid]})
        with pytest.raises(ValueError, match='no valid positions'):
            reader.accept({'source':'puzzle','focused':True,'boards':[dict(valid,fen='invalid')]})
        assert not reader.reads()
    finally:
        reader.close()


def test_live_poll_falls_back_to_screen_and_switches_back_automatically(qt,monkeypatch):
    reader_factory(monkeypatch)
    window = MainWindow()
    captures = []
    image = cv2.imread(str(Path(__file__).parent/'fixtures/chesscom-italian-white.png'))
    screenshot_placement = 'r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R'
    board = chess.Board()
    board.push_san('e4')
    direct = {'source':'chess','focused':True,'boards':[{'fen':board.fen(),'white_bottom':True}]}
    try:
        monkeypatch.setattr('chess_helper.app.foreground_kind',lambda:'browser')
        monkeypatch.setattr('chess_helper.app.capture',lambda screen: captures.append(screen) or image.copy())
        monkeypatch.setattr(window,'suggest',lambda **kw:None)
        window.source.blockSignals(True)
        window.source.setCurrentIndex(1)
        window.source.blockSignals(False)
        window.browser_reader_button.setChecked(True)
        window.browser_reader.accept(direct)
        window.start_live()
        wait(qt,lambda:window._screen_confirmed and window.tracker.board.fen()==board.fen())
        window.visible_game_end(board.fen(),'Game over')
        assert window.game_ended

        window.browser_reader.accept({'source':'puzzle','focused':True,'boards':[]})
        window.browser_reader.accept(dict(direct,focused=False))
        wait(qt,lambda:window._screen_confirmed and window.tracker.board.board_fen()==screenshot_placement)
        assert not window.game_ended
        assert captures and window.region.screen_name==screen_key(QGuiApplication.primaryScreen())

        captures.clear()
        window.browser_reader.accept(direct)
        wait(qt,lambda:window._screen_confirmed and window.tracker.board.fen()==board.fen())
        assert window.region.screen_name=='browser:chess:0'
        assert window.browser_reader_button.isChecked()
    finally:
        window.close()


def test_replaces_a_puzzle_at_the_same_location_without_a_move_highlight(qt, monkeypatch):
    window = MainWindow()
    try:
        window.source.blockSignals(True)
        window.source.setCurrentIndex(1)
        window.source.blockSignals(False)
        window._monitoring = True
        monkeypatch.setattr(window, "suggest", lambda **_: None)
        screen = QGuiApplication.primaryScreen()
        key = screen_key(screen)
        first = exact_read(chess.STARTING_FEN, True, None)
        window.live_finished(window._live_token, (key, screen.name(), first, 1024, 768), "")
        assert window._screen_confirmed

        puzzle = chess.Board("7k/2P5/8/8/8/2r5/8/K7 w - - 0 1")
        replacement = exact_read(puzzle.fen(), True, None)
        replacement.exact_fen = replacement.turn_hint = None
        answer = (key, screen.name(), replacement, 1024, 768)
        for _ in range(2):
            window.live_finished(window._live_token, answer, "")
            assert window.tracker.board.board_fen() == chess.STARTING_BOARD_FEN
        window.live_finished(window._live_token, answer, "")
        assert window._screen_confirmed
        assert window.tracker.board.board_fen() == puzzle.board_fen()
        assert window._monitoring
    finally:
        window.close()
