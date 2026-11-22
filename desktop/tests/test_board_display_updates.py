import chess
import pytest

from chess_helper import engine_library
from chess_helper.app import MainWindow
from chess_helper.core import evaluation_text
from chess_helper.engine import summarize
from chess_helper.move_advantage import comparison_rows
from chess_helper.threats import presentation
from test_app_engine import wait


@pytest.mark.parametrize(("score", "white", "black"), [
    ({"cp": -640}, "-6.40", "+6.40"),
    ({"cp": 0}, "+0.00", "+0.00"),
    ({"mate": -3}, "−M3", "+M3"),
    ({"white_share": .2}, "20%", "80%"),
    ({"cp": -100000}, "0–1", "0–1"),
])
def test_bar_formats_scores_for_the_bottom_color(score, white, black):
    assert evaluation_text(**score) == white
    assert evaluation_text(**score, white_bottom=False) == black


def test_multiple_attackers_get_a_distinct_custom_color():
    board = chess.Board("4k3/8/2n1n3/8/3Q4/8/8/4K3 b - - 0 1")
    colors = {"attack": "#ff8c73", "hanging": "#ff7185", "multiple": "#35ab9f", "mate": "#c89bff"}
    marks, messages = presentation(board, True, True, True, colors=colors)
    assert {"square": chess.D4, "kind": "hanging", "color": "#35ab9f"} in marks
    assert any("c6, e6" in message for message in messages)


def test_model_changes_and_move_only_bots_have_distinct_units():
    model, unscored = comparison_rows(
        {"white_share": .4}, [{"san": "e5", "white_share": .3}, {"san": "c5"}], False
    )
    assert model == {"move": "e5", "score": "70.0%", "change": "+10.0 pp"}
    assert unscored == {"move": "c5", "score": "—", "change": "—"}


def test_threat_worker_and_gain_arrows_follow_the_position(qt):
    window = MainWindow()
    try:
        window.source.setCurrentIndex(0)
        board = chess.Board("4k3/8/2n1n3/8/3Q4/8/8/4K3 b - - 0 1")
        window.set_position(board)
        window.threats_enabled.setChecked(True)
        wait(qt, lambda: any(m["square"] == chess.D4 for m in window.board_view.marks))
        panel = window.move_advantage
        assert {panel.engine.itemData(i) for i in range(panel.engine.count())} == set(range(len(engine_library.ENTRIES)))
        panel.show_scores.setChecked(True)
        panel.result = {"fen": board.fen(), "rows": [
            {"move": "Ncxd4", "uci": "c6d4", "score": "+0.43", "change": "+0.10"},
            {"move": "Nexd4", "uci": "e6d4", "score": "+0.31", "change": "-0.02"},
            {"move": "Ke7", "uci": "e8e7", "score": "+0.33", "change": "0.00"},
        ]}
        window.update_visuals()
        marks = [m for m in window.board_view.marks if m["kind"] == "gain_arrow"]
        assert marks == [{"square": chess.D4, "kind": "gain_arrow", "move": "c6d4",
                          "color": panel.score_color.color, "label": "+0.10"}]
        next_board = board.copy()
        next_board.push_uci("c6d4")
        assert not panel.marks(next_board)
    finally:
        window.close()


def test_arrow_rank_filters_require_enough_candidates(qt):
    window = MainWindow()
    try:
        window.recommendation_preset(1)
        assert not window.rank_second.isEnabled()
        assert not window.rank_others.isEnabled()
        window.recommendation_preset(3)
        assert window.rank_second.isEnabled()
        assert window.rank_others.isEnabled()
        window.arrow_count.setValue(2)
        assert window.rank_second.isEnabled()
        assert not window.rank_others.isEnabled()
        assert window.rank_others.isChecked()
    finally:
        window.close()


def test_stockfish_scoring_limits_are_independent_and_saved(qt, monkeypatch):
    from chess_helper.engine import EngineJob

    window = MainWindow()
    panel = window.move_advantage
    jobs = []
    run = EngineJob.run

    def record_limits(job, command, board, settings):
        if job.session is panel.session:
            jobs.append((settings.mode, settings.seconds, settings.depth, settings.multipv))
        return run(job, command, board, settings)

    monkeypatch.setattr(EngineJob, "run", record_limits)
    try:
        window.source.setCurrentIndex(0)
        window.engine_settings_button.click()
        assert window.settings_tabs.currentWidget() is window.engine_settings_page
        assert window.workspace_stack.currentWidget() is window.settings_page

        window.eval_seconds.setValue(1.2)
        window.eval_depth.setValue(24)
        panel.restore_limits({})
        assert (panel.seconds.value(), panel.depth.value()) == (1.2, 24)

        panel.mode.setCurrentText("Time")
        assert panel.depth.isHidden()
        panel.mode.setCurrentText("Depth")
        assert panel.seconds.isHidden()
        panel.mode.setCurrentText("Time + depth")
        assert not panel.seconds.isHidden() and not panel.depth.isHidden()
        panel.seconds.setValue(.2)
        panel.depth.setValue(8)
        if not window.engine_path.text():
            pytest.skip("Stockfish missing")
        panel.count.setValue(2)
        wait(qt, lambda: panel.result is not None)
        assert jobs == [("Time + depth", .2, 8, 1), ("Time + depth", .2, 8, 2)]
        assert len(panel.result["rows"]) == 2
        assert (window.eval_seconds.value(), window.eval_depth.value()) == (1.2, 24)
        panel.count.setValue(0)
        panel.mode.setCurrentText("Depth")
        window.save()
    finally:
        window.close()

    restored = MainWindow()
    try:
        panel = restored.move_advantage
        assert (panel.mode.currentText(), panel.seconds.value(), panel.depth.value()) == ("Depth", .2, 8)
        restored.toggle_compact(True)
        restored.engine_settings_button.click()
        assert restored.settings_dialog.isVisible()
        assert restored.settings_tabs.currentWidget() is restored.engine_settings_page
    finally:
        restored.close()



def test_toolbar_four_arrows_unlock_every_requested_rank(qt):
    window = MainWindow()
    try:
        window.source.setCurrentIndex(0)
        window.recommendation_preset(1)
        window.quick_arrow_count.setValue(4)
        assert window.multipv.value() == window.arrow_count.value() == 4
        board = window.tracker.board
        moves = [chess.Move.from_uci(uci) for uci in ('e2e4', 'd2d4', 'c2c4', 'g1f3')]
        lines = [{'pv': [move], 'score': chess.engine.PovScore(chess.engine.Cp(20), chess.WHITE)}
                 for move in moves]
        window.engine_progress(window.generation, summarize(board, lines[:1], 'QA'))
        window.engine_progress(window.generation, summarize(board, lines, 'QA'))
        arrows = window.board_view.arrows
        assert [arrow['move'] for arrow in arrows] == moves
        assert len({arrow['color'] for arrow in arrows}) == 4
    finally:
        window.close()
