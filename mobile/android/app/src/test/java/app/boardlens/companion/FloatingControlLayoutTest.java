package app.boardlens.companion;

import static app.boardlens.companion.FloatingControlLayout.*;
import static org.junit.Assert.*;
import org.junit.Test;

public class FloatingControlLayoutTest {
  @Test public void fittingAndResizingKeepTheWholePanelReachable() {
    Box safe = new Box(30, 60, 700, 440);
    Box small = fit(safe, -40, 600, 240, 240);
    assertEquals(new Box(30, 200, 270, 440), small);
    Box large = resize(safe, small, 500, 400, 230, 230);
    assertEquals(new Box(30, 200, 700, 440), large);
    assertEquals(new Box(30, 60, 700, 440), fit(safe, 800, 800, 800, 800));
    assertEquals(new Box(30, 200, 260, 430), resize(safe, small, -80, -80, 230, 230));
  }

  @Test public void defaultDockingLeavesTheBoardUncovered() {
    Box safe = new Box(8, 38, 408, 850);
    Box board = new Box(16, 190, 400, 574);
    Box requested = new Box(118, 38, 408, 378);
    Box panel = dockPanel(safe, requested, board, 8, 230);
    assertFalse(panel.overlaps(board));
    assertEquals(new Box(118, 582, 408, 850), panel);
    Box pill = new Box(296, 38, 408, 86);
    assertEquals(pill, dock(safe, pill, board, 8));
  }

  @Test public void occupyingTheFullScreenDoesNotMakeControlsUnreachable() {
    Box safe = new Box(8, 40, 390, 780);
    Box panel = new Box(100, 40, 390, 380);
    assertEquals(panel, dockPanel(safe, panel, safe, 8, 230));
  }
}
