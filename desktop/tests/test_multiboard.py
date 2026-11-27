import time
import chess
import chess.engine
import numpy as np
import cv2
import pytest
from pathlib import Path
from PySide6.QtGui import QGuiApplication
from chess_helper.app import MainWindow
from chess_helper.capture import screen_key
from chess_helper.recognition import Recognizer
from chess_helper.vision import Detection
from chess_helper.core import ordered_symbols
from chess_helper.engine import summarize


def test_three_boards_found_in_one_screenshot_including_duplicate_positions(render_board):
    board=chess.Board();second=board.copy();second.push_uci('e2e4')
    image=np.full((760,1800,3),28,np.uint8)
    for x,b in zip((25,590,1155),(board,second,board)):
        image[100:612,x:x+512]=render_board(b)
    reads=Recognizer().scan_all(image)
    assert len(reads)==3
    assert [r.symbols for r in reads]==[ordered_symbols(board),ordered_symbols(second),ordered_symbols(board)]


@pytest.mark.parametrize('rows,cols,size',[(1,1,128),(2,2,240),(2,4,216),(4,4,192)])
def test_discovery_finds_every_disjoint_board(rows,cols,size):
    image = cv2.imread(str(Path(__file__).parent/'fixtures/chesscom-starting-board.png'))
    tile = cv2.resize(image,(size,size),interpolation=cv2.INTER_AREA)
    grid = np.full((rows*(size+20)+20,cols*(size+20)+20,3),31,np.uint8)
    for row in range(rows):
        for col in range(cols):
            y,x = 20+row*(size+20),20+col*(size+20)
            grid[y:y+size,x:x+size] = tile
    reads = Recognizer().scan_all(grid)
    assert len(reads)==rows*cols
    assert all(read.symbols==ordered_symbols(chess.Board()) for read in reads)


def answers(render_board,boards):
    recognizer=Recognizer();key=screen_key(QGuiApplication.primaryScreen())
    result=[]
    for index,board in enumerate(boards):
        read=recognizer.read(render_board(board));read.detection=Detection(30+index*560,100,512,1.)
        result.append((key,'test display',read,1800,800))
    return result


def prepare(qt,monkeypatch):
    w=MainWindow();w.show();qt.processEvents()
    w.source.blockSignals(True);w.source.setCurrentIndex(1);w.source.blockSignals(False)
    w._monitoring=True
    monkeypatch.setattr(w,'suggest',lambda **kw:None)
    monkeypatch.setattr(w.multi,'search',lambda state:None)
    return w


def test_three_independent_boards_track_and_collapse_to_one(qt,monkeypatch,render_board):
    w=prepare(qt,monkeypatch);board=chess.Board()
    initial=answers(render_board,[board,board,board])
    for _ in range(2):w.live_finished(w._live_token,initial,'')
    assert len(w.multi.states)==2 and w.multi.count==3
    assert w.multi.grid.count()==3 and not w.boards_button.isHidden()
    assert w.workspace_stack.currentIndex()==1
    qt.processEvents()
    for button in (w.boards_button,w.focus_button):
        assert button.width()>=button.sizeHint().width()
    w.focus_button.click()
    assert w.workspace_stack.currentIndex()==0
    w.multi.layout_cards()
    assert w.workspace_stack.currentIndex()==0 and w.focus_button.isChecked()
    w.boards_button.click()
    assert w.workspace_stack.currentIndex()==1
    moved=board.copy();moved.push_uci('e2e4')
    updated=answers(render_board,[board,moved,board])
    for _ in range(2):w.live_finished(w._live_token,updated,'')
    assert w.tracker.board.fen()==chess.STARTING_FEN
    assert w.multi.states[0].tracker.board.fen()==moved.fen()
    assert w.multi.states[1].tracker.board.fen()==chess.STARTING_FEN
    for _ in range(3):w.live_finished(w._live_token,updated[0],'')
    assert not w.multi.states and w.multi.count==1
    assert w.multi.grid.count()==1 and not w.boards_button.isVisible()
    assert w.workspace_stack.currentIndex()==0
    w.close()


def test_each_secondary_board_keeps_its_own_locked_suggestions(qt,monkeypatch,render_board):
    w=prepare(qt,monkeypatch);batch=answers(render_board,[chess.Board()]*3)
    for _ in range(2):w.live_finished(w._live_token,batch,'')
    w.recommendation_preset(2)
    w.stick_to_move.setChecked(True)
    for state,move in zip(w.multi.states,('e2e4','g1f3')):
        result=summarize(state.tracker.board,[{'pv':[chess.Move.from_uci(move)],'score':chess.engine.PovScore(chess.engine.Cp(20),chess.WHITE)}],'test')
        w.multi.finished(state,state.generation,result,'',True)
    before=[s.card.move.text() for s in w.multi.states]
    for state in w.multi.states:
        newer=summarize(state.tracker.board,[{'pv':[chess.Move.from_uci('d2d4')],'score':chess.engine.PovScore(chess.engine.Cp(-30),chess.WHITE)}],'test')
        w.multi.finished(state,state.generation,newer,'',False)
    assert [s.card.move.text() for s in w.multi.states]==before
    assert [[a['move'].uci() for a in s.card.view.arrows] for s in w.multi.states] == [
        ['e2e4', 'd2d4'], ['g1f3', 'd2d4']]
    assert all(s.card.bar.cp==-30 for s in w.multi.states)
    w.stick_to_move.setChecked(False)
    assert [s.card.view.arrows[0]['move'].uci() for s in w.multi.states]==['d2d4','d2d4']
    w.close()


def test_reordered_detections_keep_identity_without_array_comparison(qt,monkeypatch,render_board):
    w=prepare(qt,monkeypatch);batch=answers(render_board,[chess.Board()]*3)
    for _ in range(2):w.live_finished(w._live_token,batch,'')
    original_region=w.region
    for _ in range(2):w.live_finished(w._live_token,list(reversed(batch)),'')
    assert w.region==original_region
    assert len(w.multi.states)==2 and w.multi.count==3
    w.close()


def test_expand_button_shows_inline_settings_and_compact_button_returns(qt):
    w=MainWindow();w.show();qt.processEvents()
    w.toggle_compact(True)
    assert w.compact_button.text()=='Expand'
    w.compact_button.click();qt.processEvents()
    assert not w._compact
    assert w.settings_tabs.parentWidget()==w.settings_page
    assert w.compact_button.text()=='Compact'
    w.compact_button.click();qt.processEvents()
    assert w._compact
    w.settings_button.click();qt.processEvents()
    assert w.settings_dialog.isVisible()
    w.close()


def test_extra_board_queue_has_a_bound_and_discards_cancelled_requests(qt):
    from threading import Event
    from chess_helper.multiboard import BoardSearches

    searches = BoardSearches(1)
    release = Event()
    completed = []
    try:
        searches.submit(lambda: release.wait(3), 0)
        low = searches.submit(lambda: completed.append('low'), -1)
        stale = searches.submit(lambda: completed.append('stale'), 1)
        searches.submit(lambda: completed.append('high'), 1)
        assert not low.running() and stale.cancel()
        release.set()
        until = time.monotonic()+3
        while not low.done() and time.monotonic()<until:
            qt.processEvents();time.sleep(.01)
        assert completed==['high','low']
    finally:
        release.set()
        searches.close()


def test_secondary_flipped_board_publishes_every_numbered_ply(qt, monkeypatch):
    from chess_helper.direct_boards import BrowserReader

    w = prepare(qt, monkeypatch)
    try:
        w.browser_reader = BrowserReader(port=0)
        w.stick_to_move.setChecked(False)
        w.only_my_color.setChecked(False)
        w.show_black.setChecked(True)
        w.overlay_enabled.setChecked(True)
        w.rank_best.setChecked(True)
        board = chess.Board()
        sequence = ("e4 e5 Nf3 Bc5 Nxe5 Nf6 d4 Bb6 Bc4 O-O Qf3 d6 Nxf7 Rxf7 "
                    "Bxf7+ Kxf7 e5 dxe5 dxe5 Bg4 Qb3+ Be6 Qg3")
        for san in sequence.split():
            board.push_san(san)
        boards = [{"index": i, "board_id": str(i) * 32, "white_bottom": False,
                   "fen": fen, "exact": True}
                  for i, fen in enumerate((chess.STARTING_FEN, board.fen()))]
        batch = w.browser_reader.accept({"source": "fixture", "visible": True,
                                         "focused": False, "boards": boards})
        for _ in range(2):
            w.live_finished(w._live_token, batch, '')
        state, = w.multi.states
        w.predict_continuations.setChecked(True)
        w.prediction_plies.setValue(4)
        moves = [chess.Move.from_uci(uci) for uci in ("f6e4", "g3f4", "f7g8", "f4e4")]
        result = summarize(board, [{"pv": moves}], "fixture", allow_unscored=True)
        w.multi.finished(state, state.generation, result, '', False)
        w.publish_reader_hints()
        hints = w.browser_reader.hints["browser:fixture:1"]
        assert hints["fen"] == board.fen()
        assert [(a["lookahead_ply"], a["move"]) for a in hints["arrows"]] == [
            (i, move.uci()) for i, move in enumerate(moves, 1)]
        assert len({a["color"] for a in hints["arrows"]}) == 4
    finally:
        w.close()
