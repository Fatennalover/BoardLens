import time
import chess
import chess.engine
import pytest
from chess_helper.app import MainWindow
from chess_helper.engine import summarize


def result(board,move,cp=20):
    probe=board.copy();first=chess.Move.from_uci(move);probe.push(first)
    pv=[first]+([] if probe.is_game_over() else [next(iter(probe.legal_moves))])
    return summarize(board,[{'pv':pv,'score':chess.engine.PovScore(chess.engine.Cp(cp),chess.WHITE),'depth':12}], 'test engine')


def test_first_move_stays_locked_through_progress_and_final_but_eval_updates(qt):
    w=MainWindow();w.stick_to_move.setChecked(True)
    w.show_reply.setChecked(False);w.predict_continuations.setChecked(False);w.recommendation_preset(1)
    board=w.tracker.board
    a=result(board,'e2e4');b=result(board,'d2d4',-80)
    w.engine_progress(w.generation,a)
    assert [x['move'].uci() for x in w.board_view.arrows]==['e2e4']
    w.engine_progress(w.generation,b)
    w.engine_finished(w.generation,b,'')
    assert w.result['lines'][0]['move']=='d2d4'
    assert [x['move'].uci() for x in w.board_view.arrows]==['e2e4']
    assert 'e4' in w.simple_label.text() and 'locked' in w.simple_label.text()
    assert not w.reply_label.text() and w.eval_bar.cp==-80
    w.stick_to_move.setChecked(False)
    assert w.board_view.arrows[0]['move'].uci()=='d2d4'
    assert 'd4' in w.simple_label.text()
    w.close()


def test_lock_preserves_same_position_reanalysis_and_releases_for_new_board(qt):
    w=MainWindow()
    w.show_reply.setChecked(False);w.predict_continuations.setChecked(False);w.recommendation_preset(1)
    w.result=result(w.tracker.board,'e2e4')
    w.stick_to_move.setChecked(True)
    w.invalidate(preserve_eval=True)
    assert w.result is None
    assert [x['move'].uci() for x in w.board_view.arrows]==['e2e4']
    w.engine_progress(w.generation,result(w.tracker.board,'d2d4'))
    assert w.board_view.arrows[0]['move'].uci()=='e2e4'
    w.tracker.board.push_uci('e2e4');w.invalidate();w.refresh_board()
    w.engine_progress(w.generation,result(w.tracker.board,'e7e5'))
    assert [x['move'].uci() for x in w.board_view.arrows]==['e7e5']
    w.close()


def test_scan_now_releases_pin_and_setting_persists(qt,monkeypatch):
    w=MainWindow();w.result=result(w.tracker.board,'e2e4')
    w.stick_to_move.setChecked(True);w.save()
    monkeypatch.setattr(w,'request_scan',lambda **kw:None)
    w.scan_now()
    assert w._pinned_result is None and not w.board_view.arrows
    assert w.stick_to_move.isChecked()
    w.close()
    again=MainWindow()
    assert again.stick_to_move.isChecked() and again._pinned_result is None
    again.close()



def test_lock_keeps_four_suggestions_replies_and_lookahead(qt):
    w = MainWindow()
    try:
        board = w.tracker.board
        w.recommendation_preset(4)
        w.show_reply.setChecked(True)
        w.show_black.setChecked(True)
        w.predict_continuations.setChecked(True)
        w.prediction_plies.setValue(4)
        w.stick_to_move.setChecked(True)

        def search(*paths):
            entries = []
            for number, path in enumerate(paths):
                score = chess.engine.PovScore(chess.engine.Cp(30 - number), chess.WHITE)
                entries.append({'pv': [chess.Move.from_uci(uci) for uci in path.split()],
                                'score': score, 'depth': 12})
            return summarize(board, entries, 'test engine')

        w.engine_progress(w.generation, search('e2e4'))
        complete = search('d2d4 d7d5', 'g1f3 d7d5', 'e2e4 e7e5 g1f3 b8c6', 'c2c4 e7e5')
        w.engine_finished(w.generation, complete, '')
        expected = ['e2e4', 'd2d4', 'g1f3', 'c2c4']
        assert [line['move'] for line in w.displayed_result(w.result)['lines']] == expected
        assert w.reply_label.text()
        assert '#4 White' in w.lines.toPlainText()
        assert [(a['lookahead_ply'], a['move'].uci()) for a in w.board_view.arrows if a.get('lookahead_ply')] == [
            (1, 'e2e4'), (2, 'e7e5'), (3, 'g1f3'), (4, 'b8c6')]
        assert [a['move'].uci() for a in w.board_view.arrows if not a.get('lookahead_ply')] == expected[1:]

        data = w.phone.board('primary', 'Board 1', board, True, w.result,
                             w.displayed_result(w.result), w.board_view.arrows)
        assert [line['move'] for line in data['lines']] == expected
        assert all(line['reply'] for line in data['lines'])

        # Changing the selection keeps the first two locked and exposes the fixed order again when restored.
        w.recommendation_preset(2)
        assert [a['move'].uci() for a in w.board_view.arrows if not a.get('lookahead_ply')] == ['d2d4']
        w.recommendation_preset(4)
        assert [a['move'].uci() for a in w.board_view.arrows if not a.get('lookahead_ply')] == expected[1:]
        w.prediction_plies.setValue(2)
        assert [a['lookahead_ply'] for a in w.board_view.arrows if a.get('lookahead_ply')] == [1, 2]
    finally:
        w.close()
