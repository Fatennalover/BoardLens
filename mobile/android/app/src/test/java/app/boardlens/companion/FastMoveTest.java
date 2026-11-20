package app.boardlens.companion;
import android.app.Application;
import android.graphics.Rect;
import android.os.Looper;
import java.lang.reflect.*;
import java.util.*;
import org.junit.*;
import org.junit.runner.RunWith;
import org.robolectric.*;
import org.robolectric.annotation.Config;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class) @Config(sdk=35,application=Application.class)
public class FastMoveTest {
 private static final String START="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";
 private void set(Object o,String n,Object v)throws Exception{Field f=o.getClass().getDeclaredField(n);f.setAccessible(true);f.set(o,v);}
 @Test public void fastSingleAndSkippedMovesKeepTurnAndHistory(){
  ChessPosition tracked=new ChessPosition(START),visible=new ChessPosition(START);
  String[] moves={"e2e4","e7e5","g1f3","b8c6","f1b5","a7a6","b5a4","g8f6"};
  for(int i=0;i<moves.length;i++){
   visible=visible.play(moves[i]);if(i%3==0)continue;
   tracked=ChessPosition.sync(tracked,visible.placement(),"Auto");assertNotNull(tracked);assertEquals(visible.fen(),tracked.fen());
  }
 }
 @Test public void cancelledMoveRestoresWhiteTurnAndHistory(){
  ChessPosition real=new ChessPosition(START).play("e2e4").play("e7e5"),preview=real.play("g1f3");
  assertFalse(preview.white);
  ChessPosition back=ChessPosition.sync(preview,real.placement(),"Auto");
  assertNotNull(back);assertEquals(real.fen(),back.fen());assertTrue(back.white);
 }
 @Test public void terminalBoardsHaveNoMoveToSuggest(){
  ChessPosition mate=new ChessPosition("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1"),stale=new ChessPosition("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1");
  assertTrue(mate.legal().isEmpty());assertTrue(mate.inCheck(false));assertTrue(stale.legal().isEmpty());assertFalse(stale.inCheck(false));
 }
 @Test public void unmatchedLegalLookingFrameCannotResetTurn(){
  ChessPosition old=new ChessPosition(START).play("e2e4");
  String impossible="rnbqkbnr/pppppppp/8/8/3PP3/8/PPP2PPP/RNBQKBNR";
  assertNull(ChessPosition.sync(old,impossible,"Auto"));assertFalse(old.white);
  assertNotNull(ChessPosition.sync(old,impossible,"Auto",true));
 }
 @Test public void checkmateCancelsArrowsAndReportsGameOver()throws Exception{
  var c=Robolectric.buildService(ScreenService.class).create();ScreenService service=c.get();PhoneSettings prefs=new PhoneSettings(service);prefs.p.edit().clear().apply();
  set(service,"settings",prefs);set(service,"overlay",new ArrowOverlay(service));set(service,"lastArrows",List.of("e2e4"));ScreenService.running=true;
  try{
   ChessPosition mate=new ChessPosition("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1");set(service,"position",mate);
   Method analyze=ScreenService.class.getDeclaredMethod("analyze",ChessPosition.class,Rect.class,boolean.class);analyze.setAccessible(true);analyze.invoke(service,mate,new Rect(0,100,400,500),true);
   assertEquals("Game over · Checkmate",ScreenService.status);
   Field arrows=ScreenService.class.getDeclaredField("lastArrows");arrows.setAccessible(true);assertEquals(List.of(),arrows.get(service));
  }finally{c.destroy();Shadows.shadowOf(Looper.getMainLooper()).idle();}
 }
 @Test public void staleRootWithCurrentTokenCannotReplaceNewBoardArrows()throws Exception{
  var c=Robolectric.buildService(ScreenService.class).create();ScreenService service=c.get();
  PhoneSettings settings=new PhoneSettings(service);settings.p.edit().clear().apply();
  ChessPosition old=new ChessPosition(START),current=old.play("e2e4");
  set(service,"settings",settings);set(service,"position",current);set(service,"overlay",new ArrowOverlay(service));
  ScreenService.running=true;
  try{
   Method publish=ScreenService.class.getDeclaredMethod("publishMoves",PhoneEngine.Result.class,ChessPosition.class,Rect.class,boolean.class,long.class,boolean.class);publish.setAccessible(true);
   publish.invoke(service,new PhoneEngine.Result(old.fen(),"late",List.of(new PhoneEngine.Line("d2d4",0,null,1,List.of("d2d4")))),old,new Rect(0,100,400,500),true,0L,true);
   Field arrows=ScreenService.class.getDeclaredField("lastArrows");arrows.setAccessible(true);assertEquals(List.of(),arrows.get(service));
  }finally{c.destroy();Shadows.shadowOf(Looper.getMainLooper()).idle();}
 }
}
