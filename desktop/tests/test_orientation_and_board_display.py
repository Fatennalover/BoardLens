import sys
import chess,cv2,numpy as np,pytest
from chess_helper.coordinates import rank_orientation,templates
from chess_helper.core import ordered_symbols,PositionTracker
from chess_helper.recognition import Read,position_from_read
from chess_helper.app import MainWindow
from chess_helper.game_end import reason,read_text


def labels(bottom,size=640):
    image=np.full((size,size,3),130,np.uint8);cell=size//8
    for row in range(8):
        digit=8-row if bottom else row+1
        mask=next(a for n,a in templates() if n==digit)
        mask=cv2.resize(mask,(max(5,cell//10),max(10,cell//5)))
        y=row*cell+cell//30;x=cell//20
        image[y:y+mask.shape[0],x:x+mask.shape[1]]=np.where(mask[...,None]>.3,230,130)
    return image

@pytest.mark.parametrize('bottom',[True,False])
@pytest.mark.parametrize('size',[640,1328])
def test_rank_labels_override_advanced_pawn_guess(bottom,size):
    assert rank_orientation(labels(bottom,size)) is bottom

def test_no_coordinate_evidence_does_not_invent_orientation():
    assert rank_orientation(np.zeros((640,640,3),np.uint8)) is None
    image=labels(False);image[160:]=130
    assert rank_orientation(image) is None

def test_flip_and_two_moves_retain_turn_metadata():
    board=chess.Board();board.push_uci('e2e4');board.push_uci('e7e5')
    real=board.copy();real.push_uci('g1f3');real.push_uci('b8c6')
    read=Read(ordered_symbols(real,False),np.ones(64),np.ones((64,13)),False,None,np.zeros((64,64,3),np.uint8))
    synced,known=position_from_read(read,previous=board)
    assert synced.fen()==real.fen() and known and synced.turn==chess.WHITE

@pytest.mark.parametrize('text',['White won by resignation','You lost on time','Draw by agreement','Game aborted','Black wins','Checkmate'])
def test_visible_endings(text):assert reason(text)==text
@pytest.mark.parametrize('text',['Resign','Offer draw','Game review','White to move','Resign from this game?'])
def test_controls_are_not_game_results(text):assert reason(text) is None

@pytest.mark.skipif(sys.platform!='darwin',reason='macOS native OCR')
def test_native_ocr_reads_actual_result_pixels():
    image=np.full((160,850,3),245,np.uint8);cv2.putText(image,'White won by resignation',(20,90),cv2.FONT_HERSHEY_SIMPLEX,1.2,(15,15,15),2)
    assert any(reason(text) for text in read_text(image))


def test_screen_eval_moves_resizes_and_keeps_custom_bounds(qt):
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QGuiApplication
    from chess_helper.eval_overlay import EvaluationOverlay
    panel=EvaluationOverlay();screen=QGuiApplication.primaryScreen()
    try:
        panel.set_score(QRect(200,100,400,400),True,160,None,screen);before=panel.geometry()
        panel._gesture('begin',10,10);panel._gesture('end',60,40)
        assert panel.x()==before.x()+50 and panel.y()==before.y()+30
        panel._gesture('begin',0,0,True);panel._gesture('end',35,80)
        saved=panel.geometry();panel.set_score(QRect(100,100,400,400),False,None,None,screen)
        assert panel.geometry()==saved and panel.target>.5
        assert panel.width()==before.width()+35 and panel.height()==before.height()+80
        panel.reset_position();panel.set_score(QRect(200,100,400,400),True,160,None,screen)
        assert panel.geometry()==before
    finally:panel.close()


def test_browser_evaluation_works_with_arrows_off_and_uses_separate_engine(qt):
    from chess_helper.direct_boards import BrowserReader,exact_read
    from chess_helper.engine import summarize
    from chess.engine import PovScore,Cp
    w=MainWindow();reader=BrowserReader(port=0);w.browser_reader=reader
    try:
        board=w.tracker.board
        evaluation=summarize(board,[{'pv':[chess.Move.from_uci('e2e4')],'score':PovScore(Cp(185),True)}],'Evaluation engine')
        w.evaluations.cache[board.fen()]=evaluation
        w._last_read=exact_read(board.fen(),False,'browser:qa:0');w._screen_confirmed=True;w._monitoring=True
        w.screen_eval_enabled.setChecked(True);w.overlay_enabled.setChecked(False);w.publish_reader_hints()
        hint=reader.hints['browser:qa:0'];assert hint['arrows']==[]
        assert hint['evaluation']['cp']==185 and hint['evaluation']['provider']=='Evaluation engine'
        w.screen_eval_enabled.setChecked(False);w.publish_reader_hints();assert reader.hints['browser:qa:0']['evaluation']['cp']==185
        w.browser_eval_enabled.setChecked(False);w.publish_reader_hints()
        assert reader.evaluation_visible is False
        assert reader.hints['browser:qa:0']['evaluation'] is None
    finally:w.close()

@pytest.mark.parametrize("bottom",[True,False])
def test_tiny_coordinate_labels_abstain_instead_of_false_flip(bottom):
    assert rank_orientation(labels(bottom,320)) in (None,bottom)


def test_result_at_start_position_survives_board_loss_until_manual_reset(qt):
    w=MainWindow()
    try:
        w._monitoring=True
        w.visible_game_end(w.tracker.board.fen(),'Game aborted')
        assert w.game_ended and w._ended_placement==chess.STARTING_BOARD_FEN
        message=w.status_label.text()
        w.live_finished(w._live_token,None,'')
        assert w.game_ended and w.status_label.text()==message
        w.new_game();assert not w.game_ended
    finally:w.close()


@pytest.mark.parametrize('bottom',[True,False])
def test_first_read_after_an_opening_move_keeps_the_actual_turn(bottom):
    board=chess.Board()
    board.push_uci('d2d4')
    read=Read(ordered_symbols(board,bottom),np.ones(64),np.ones((64,13)),
              bottom,None,np.zeros((64,64,3),np.uint8))
    actual,known=position_from_read(read)
    assert known
    assert actual.fen()==board.fen()
    assert actual.turn is chess.BLACK


def test_arrow_engine_profiles_roundtrip_through_companion(qt):
    window=MainWindow()
    try:
        bridge=window.phone
        profiles=[dict(engine='stockfish',color='#eeaa77',seconds=.3,depth=9,moves=2,plies=4,rating=1550)]
        bridge.apply_settings({'extra_engines':profiles,'primary_arrow_color':'#22bb88'})
        assert window.extra_engines.profiles[0]['color']=='#eeaa77'
        assert window.extra_engines.profiles[0]['plies']==4
        assert window.extra_engines.primary_color=='#22bb88'
    finally:
        window.close()
