package app.boardlens.companion;

import static org.junit.Assert.assertEquals;
import java.util.List;
import org.junit.Test;

public class MoveAdvantageTest {
    @Test public void deltaIsExpressedForTheMover() {
        var current = new PhoneEngine.Line("e7e5", -40, null, 10, List.of());
        var candidate = new PhoneEngine.Line("c7c5", -20, null, 10, List.of());
        assertEquals("-0.20", MoveAdvantageDialog.change(current, candidate, -1));
        assertEquals("+0.20", MoveAdvantageDialog.change(current, candidate, 1));
    }

    @Test public void mateDoesNotUseAnArtificialPawnValue() {
        var current = new PhoneEngine.Line("f6g4", -540, null, 10, List.of());
        var mate = new PhoneEngine.Line("h4h2", null, -1, 10, List.of());
        assertEquals("Mate in 1", MoveAdvantageDialog.score(mate, -1));
        assertEquals("Mate changes", MoveAdvantageDialog.change(current, mate, -1));
    }
}
