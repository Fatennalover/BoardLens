package app.boardlens.companion;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertSame;
import static org.junit.Assert.assertTrue;
import java.util.List;
import org.junit.Test;

public class CoachPanelTest {
    @Test public void showsOnlyRequestedCurrentMovesAndExplainsTheReply() {
        var board = new ChessPosition(ChessPosition.START_FEN);
        var first = new PhoneEngine.Line("e2e4", 20, null, 10, List.of("e2e4", "c7c5"));
        var second = new PhoneEngine.Line("g1f3", 12, null, 10, List.of("g1f3"));
        var recommendation = new PhoneEngine.Result(board.fen(), "Stockfish", List.of(first, second));
        assertSame(recommendation, CoachPanel.currentResult(board, recommendation));
        assertEquals("c7c5", CoachPanel.reply(board, first));
        assertEquals("", CoachPanel.reply(board, second));
        assertNull(CoachPanel.currentResult(board.play("e2e4"), recommendation));
        assertEquals("", CoachPanel.reply(board.play("e2e4"), first));
    }

    @Test public void evaluationFollowsTheBottomSideWithoutFlippingTheWhiteShare() {
        var line = new PhoneEngine.Line("e7e5", -64, null, 10, List.of("e7e5"));
        var white = LocalEngines.score("Stockfish", line);
        var black = LocalEngines.orient(white, false);
        assertEquals("-0.64", white.badge());
        assertEquals("+0.64", black.badge());
        assertTrue(black.text().contains("Black’s perspective"));
        assertEquals(white.whiteShare(), black.whiteShare(), 0f);
    }
}
