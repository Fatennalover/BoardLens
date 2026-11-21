package app.boardlens.companion;

import org.junit.Test;
import static org.junit.Assert.*;

public class PracticeLineTest {
  @Test public void scanKeepsHistoryAndReviewCanBranchFromAnyMove() {
    ChessPosition scanned = new ChessPosition(ChessPosition.START_FEN).play("e2e4").play("e7e5");
    PracticeLine line = new PracticeLine(scanned);
    assertEquals(3, line.size());
    assertEquals("1. e4", line.label(1));
    assertEquals("1… e5", line.label(2));
    PracticeLine forecast = PracticeLine.fromHere(line.at(1));
    assertTrue(forecast.play("c7c5"));
    assertEquals("1… c5", forecast.label(1));
    assertEquals(scanned.fen(), line.last().fen());
    assertEquals(line.save(), PracticeLine.restore(line.save()).save());
  }

  @Test public void changingTurnKeepsPiecesAndClearsEarlierMoves() {
    var line = new PracticeLine(new ChessPosition(ChessPosition.START_FEN));
    assertTrue(line.play("e2e4"));
    assertTrue(line.setTurn(true));
    assertEquals(1, line.size());
    assertEquals(-1, line.last().ep);
    assertTrue(line.last().white);
    assertEquals('P', line.last().b[ChessPosition.square("e4")]);
    assertFalse(line.play("e7e5"));
  }

  @Test public void mateAndDrawOutcomesFollowTheReviewedLine() {
    var mate = new PracticeLine(new ChessPosition("6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1"));
    assertTrue(mate.play("e1e8"));
    assertEquals("1. Re8#", mate.label(1));
    assertEquals("White wins · checkmate", PracticeLine.outcome(mate.last(), false));
    assertFalse(mate.setTurn(true));
    assertTrue(mate.undo());
    assertEquals("", PracticeLine.outcome(mate.last(), false));

    var draw = new PracticeLine(new ChessPosition(ChessPosition.START_FEN));
    for (int i = 0; i < 2; i++) for (String move : new String[]{"g1f3","g8f6","f3g1","f6g8"}) {
      assertTrue(draw.play(move));
    }
    assertEquals("", PracticeLine.outcome(draw.last(), false));
    assertEquals("Draw · repetition", PracticeLine.outcome(draw.last(), true));
  }
}
