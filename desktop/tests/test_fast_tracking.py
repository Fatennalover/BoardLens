import chess
import numpy as np
import pytest
from PySide6.QtCore import QRect,Qt
from PySide6.QtGui import QGuiApplication
from chess_helper.core import ordered_symbols
from chess_helper.recognition import Read,position_from_read
from chess_helper.eval_overlay import EvaluationOverlay,panel_rect
from chess_helper.app import MainWindow
from chess_helper.core import PositionTracker
from chess_helper.engine import summarize

def read(board):
    return Read(ordered_symbols(board),np.ones(64),np.ones((64,13)),True,None,np.zeros((64,64,3),np.uint8))

def test_unmatched_frame_does_not_reset_a_continuously_tracked_turn():
    previous=chess.Board();previous.push_uci('e2e4')
    bad=chess.Board('rnbqkbnr/pppppppp/8/8/3PP3/8/PPP2PPP/RNBQKBNR w KQkq - 0 1')
    with pytest.raises(ValueError,match='complete legal move'):position_from_read(read(bad),previous=previous)
    assert previous.turn==chess.BLACK
    actual=previous.copy();actual.push_uci('c7c5');actual.push_uci('g1f3')
    synced,known=position_from_read(read(actual),previous=previous)
    assert synced.fen()==actual.fen() and known

def test_passive_evaluation_panel_retains_score_while_pending_and_stays_inside_monitor(qt):
    overlay=EvaluationOverlay();screen=QGuiApplication.primaryScreen();safe=screen.availableGeometry()
    try:
        for board in (QRect(safe.left(),safe.top(),safe.width(),safe.height()),QRect(100,100,400,400)):
            assert safe.contains(panel_rect(board,safe))
        overlay.set_score(QRect(100,100,400,400),True,180,None,screen)
        target=overlay.target;overlay.fraction=.7
        overlay.set_score(QRect(100,100,400,400),True,None,None,screen)
        assert overlay.target==target and overlay.fraction==.7
        assert not overlay.windowFlags()&Qt.WindowType.WindowTransparentForInput
        assert overlay.windowFlags()&Qt.WindowType.WindowDoesNotAcceptFocus
        assert not overlay.grab().toImage().isNull()
    finally:overlay.close()

def test_completed_primary_move_is_shown_before_optional_replies_with_early_off(qt):
    w=MainWindow()
    try:
        w.early_suggestions.setChecked(False)
        board=chess.Board();w.tracker=PositionTracker(board)
        result=summarize(board,[{'pv':[chess.Move.from_uci('e2e4')]}],'QA',allow_unscored=True)
        result.update(primary_complete=True,continuation_pending=True)
        w.engine_progress(w.generation,result)
        assert w.board_view.arrows and w.board_view.arrows[0]['move']==chess.Move.from_uci('e2e4')
        assert 'Move ready' in w.status_label.text()
    finally:w.close()


def test_cancelled_drag_restores_prior_turn_and_history():
    real=chess.Board()
    for move in ('e2e4','e7e5'):real.push_uci(move)
    tracker=PositionTracker(real);preview=real.copy();preview.push_uci('g1f3')
    assert tracker.update(ordered_symbols(preview))[0]=='moved' and tracker.board.turn==chess.BLACK
    assert tracker.update(ordered_symbols(real))[0]=='moved'
    assert tracker.board.fen()==real.fen() and tracker.board.turn==chess.WHITE
