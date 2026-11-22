from copy import deepcopy
import chess,chess.engine,pytest
from chess_helper.core import SearchSettings
from chess_helper.engine import EngineJob,summarize
from chess_helper.app import MainWindow

@pytest.mark.parametrize('kind',['maia2','maia3','tiny17'])
def test_prediction_length_changes_real_number_of_provider_calls(monkeypatch,kind):
    job=EngineJob();calls=[]
    def one(engine,board,settings):
        calls.append(board.fen());move=next(iter(board.legal_moves));r=summarize(board,[{'pv':[move]}],'provider',allow_unscored=True);r['elapsed']=0;return r
    monkeypatch.setattr(job,'_search_once',one)
    result=job._search(None,chess.Board(),SearchSettings(engine_kind=kind,prediction_plies=5,prediction_seconds=3))
    assert len(calls)==5 and len(result['lines'][0]['pv_moves'])==5
    assert result['prediction']['completed_plies']==5
    calls.clear();job._search(None,chess.Board(),SearchSettings(engine_kind=kind,prediction_plies=1))
    assert len(calls)==1

@pytest.mark.parametrize("budget,expected_passes", [(.1, 1), (.5, 2)])
def test_reply_budget_stops_new_passes_without_hiding_primary_move(monkeypatch, budget, expected_passes):
    import chess_helper.engine as module
    clock=[0.];calls=[];job=EngineJob();updates=[]
    monkeypatch.setattr(module.time,'monotonic',lambda:clock[0]);job.on_update=lambda r:updates.append(deepcopy(r))
    def one(engine,board,settings):
        calls.append(settings);clock[0]+=.3;r=summarize(board,[{'pv':[next(iter(board.legal_moves))]}],'Maia',allow_unscored=True);r['elapsed']=.3;return r
    monkeypatch.setattr(job,'_search_once',one)
    r=job._search(None,chess.Board(),SearchSettings(engine_kind='maia3',prediction_plies=8,prediction_seconds=budget))
    assert len(calls)==expected_passes and r['prediction']['budget_exhausted']
    assert len(updates[0]['lines'][0]['pv_moves'])==1
    assert all(u['lines'][0]['move']==r['lines'][0]['move'] for u in updates)
    assert all(settings.seconds <= budget for settings in calls[1:])

def test_maia_controls_sync_and_save_without_enabling_fake_depth(qt):
    w=MainWindow()
    try:
        from chess_helper.engine_library import ENTRIES
        for identity in ('maia2','maia3','tiny17'):
            match=next((i for i,e in enumerate(ENTRIES) if e.identity==identity),None)
            if match is None:continue
            w.engine_kind.setCurrentIndex(match)
            w.phone.apply_settings({'prediction_plies':7,'prediction_seconds':1.7})
            s=w.search_settings();assert s.prediction_plies==7 and s.prediction_seconds==1.7
            assert w.prediction_plies.isEnabled() and w.prediction_seconds.isEnabled()
            assert not w.depth.isEnabled()
            if identity.startswith('maia'):assert not w.seconds.isEnabled()
        w.save(quiet=True);w.restore();assert w.search_settings().prediction_plies==7
        values,schema=w.phone.schema();assert values['prediction_seconds']==1.7
        w.predict_continuations.setChecked(False);assert not w.prediction_plies.isEnabled()
    finally:w.close()

def test_phone_does_not_finish_when_only_partial_recommendation_is_ready(qt):
    w=MainWindow()
    try:
        a=w.phone.analysis;a.state={'status':'thinking'};g=a.generation
        a.finish(g,'evaluation',{'lines':[{}]},'',True)
        a.finish(g,'recommendation',{'lines':[{}],'continuation_pending':True},'',False)
        assert a.state['status']=='thinking'
        a.finish(g,'recommendation',{'lines':[{}],'continuation_pending':False},'',True)
        assert a.state['status']=='ready'
    finally:w.close()

def test_reply_failure_retains_valid_primary_recommendation(monkeypatch):
    job=EngineJob();calls=[]
    def one(engine,board,settings):
        calls.append(1)
        if len(calls)>1:raise ValueError('No follow-up move')
        r=summarize(board,[{'pv':[chess.Move.from_uci('e2e4')]}],'bot',allow_unscored=True);r['elapsed']=0;return r
    monkeypatch.setattr(job,'_search_once',one)
    r=job._search(None,chess.Board(),SearchSettings(engine_kind='tiny17'))
    assert r['lines'][0]['move']=='e2e4' and r['prediction']['error']=='No follow-up move'


def test_coach_fills_missing_replies_for_each_candidate(monkeypatch):
    job = EngineJob()
    job.reply_for_every_move = True
    calls = []
    updates = []
    job.on_update = updates.append

    def search(_, board, settings):
        calls.append((board.peek().uci() if board.move_stack else None, settings.multipv))
        paths = (("e2e4", "e7e5"), ("d2d4",), ("g1f3",)) if board.turn else (("e7e5",),)
        return summarize(board, [{"pv": [chess.Move.from_uci(uci) for uci in path]} for path in paths],
                         "Test Coach", allow_unscored=True)

    monkeypatch.setattr(job, "_search_once", search)
    result = job._search(None, chess.Board(), SearchSettings(multipv=3, prediction_plies=2))
    assert calls == [(None, 3), ("d2d4", 1), ("g1f3", 1)]
    assert [line["reply_move"] for line in result["lines"]] == ["e7e5", "e7e5", "e7e5"]
    assert updates and updates[0]["continuation_pending"]


def test_lookahead_is_available_from_board_toolbar(qt):
    from PySide6.QtWidgets import QDialog

    window = MainWindow()
    try:
        window.show()
        for compact in (False, True):
            window.toggle_compact(compact)
            window.resize(window.minimumSize())
            for page in (0, 1):
                window.workspace_stack.setCurrentIndex(page)
                qt.processEvents()
                assert window.lookahead_button.isVisible()
                container = window.workspace_toolbar if compact else window.analysis_options_bar
                preceding = window.stop_button if compact else window.quick_arrows
                assert window.lookahead_button.parentWidget() is container
                assert container.rect().contains(window.lookahead_button.geometry())
                assert preceding.geometry().right() < window.lookahead_button.geometry().left()

        window.lookahead_button.click()
        dialog = next(dialog for dialog in window.findChildren(QDialog) if dialog.windowTitle() == "Look ahead")
        assert dialog.isVisible()
        assert window.lookahead_count.isEnabled()
        assert window.lookahead_budget.isVisible()
        dialog.accept()
    finally:
        window.close()
