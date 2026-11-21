package app.boardlens.companion;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;
import java.util.List;
import org.junit.Test;

public class CoachPanelTest {
    @Test public void showsOnlyRequestedCurrentMovesAndExplainsTheReply() {
        var board = new ChessPosition(ChessPosition.START_FEN);
        var first = new PhoneEngine.Line("e2e4", 20, null, 10, List.of("e2e4", "c7c5"));
        var second = new PhoneEngine.Line("g1f3", 12, null, 10, List.of("g1f3"));
        var recommendation = new PhoneEngine.Result(board.fen(), "Stockfish", List.of(first, second));
        String text = CoachPanel.notes(board, recommendation, null, 1, true, "Waiting.");
        assertTrue(text.contains("White to move · Stockfish"));
        assertTrue(text.contains("Occupies a central square."));
        assertTrue(text.contains("Likely reply c5."));
        assertFalse(text.contains("Nf3"));

        String current = CoachPanel.notes(board.play("e2e4"), recommendation, null, 3, true, "Waiting.");
        assertTrue(current.contains("Black to move"));
        assertTrue(current.contains("Waiting."));
        assertFalse(current.contains("Likely reply"));
    }
}
