package app.boardlens.companion;
import org.junit.*;
import static org.junit.Assert.*;
@org.junit.runner.RunWith(org.robolectric.RobolectricTestRunner.class)
@org.robolectric.annotation.Config(sdk=35,application=android.app.Application.class)
public class ReadOrientationTest {
 static final String START=ChessPosition.START_FEN;
 @Test public void flippedDisplayKeepsCanonicalBoardAfterTwoFastMoves(){
  var old=new ChessPosition(START).play("e2e4").play("e7e5");var real=old.play("g1f3").play("b8c6");
  var wrong=new BoardReader.Read(new android.graphics.Rect(0,0,400,400),ChessPosition.rotatePlacement(real.placement()),true,1);
  var read=ScreenService.resolveOrientation(wrong,old,"Auto");assertFalse(read.whiteBottom());assertEquals(real.placement(),read.placement());
  assertEquals(real.fen(),ChessPosition.sync(old,read.placement(),"Auto").fen());
 }
 @Test public void resultPhrasesCoverResignTimeoutDrawButNotButtons(){
  for(String s:new String[]{"White won by resignation","You lost on time","Draw by agreement","Game aborted","Checkmate"})assertEquals(s,GameEndText.reason(s));
  for(String s:new String[]{"Resign","Game review","White to move","Offer draw"})assertNull(GameEndText.reason(s));
 }
}
