import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import chess
import pytest

from chess_helper.app import MainWindow
from chess_helper.direct_boards import BrowserReader, exact_read
from chess_helper.engine import summarize


def test_browser_coach_keeps_current_moves_and_can_run_without_overlays(qt):
    window = MainWindow()
    reader = BrowserReader(port=0)
    window.browser_reader = reader
    try:
        board = window.tracker.board
        window.recommendation_preset(5)
        candidates = ['e2e4', 'd2d4', 'c2c4', 'g1f3', 'b1c3']
        result = summarize(board, [
            {'pv': [chess.Move.from_uci(move), chess.Move.from_uci('e7e5')],
             'score': chess.engine.PovScore(chess.engine.Cp(20), chess.WHITE)}
            for move in candidates
        ], 'Coach test engine')
        window.result = result
        identity = 'browser:qa:0'
        window._last_read = exact_read(board.fen(), chess.WHITE, identity)
        window._screen_confirmed = True
        window._monitoring = True
        window.overlay_enabled.setChecked(False)
        window.browser_eval_enabled.setChecked(False)
        window.result = result
        window.publish_reader_hints()
        hint = reader.hints[identity]
        assert hint['arrows'] == [] and hint['evaluation'] is None
        assert [move['san'] for move in hint['coach']['moves']] == ['e4', 'd4', 'c4', 'Nf3', 'Nc3']
        assert hint['coach']['moves'][0]['reply_simple']
        assert hint['coach']['engine'] == 'Coach test engine'

        board.push_san('d4')
        window._last_read = exact_read(board.fen(), chess.WHITE, identity)
        window.publish_reader_hints()
        assert reader.hints[identity]['coach']['side'] == 'Black'
        assert reader.hints[identity]['coach']['moves'] == []
    finally:
        window.close()


def test_retired_browser_move_endpoint_rejects_even_a_paired_reader():
    reader = BrowserReader(port=0)
    try:
        url = f'http://127.0.0.1:{reader.port}/claim-play'
        request = Request(url, data=json.dumps({'move': 'e2e4'}).encode(),
                          headers={'Authorization': 'Bearer ' + reader.token})
        with pytest.raises(HTTPError) as error:
            urlopen(request, timeout=2)
        assert error.value.code == 404
    finally:
        reader.close()
