package app.boardlens.companion;
import android.app.Application;import org.junit.*;import org.junit.runner.RunWith;import org.robolectric.*;import org.robolectric.annotation.*;import java.io.*;import java.lang.reflect.*;import java.util.*;import java.util.concurrent.*;import static org.junit.Assert.*;
@RunWith(RobolectricTestRunner.class) @Config(sdk=35,application=Application.class)
public class EngineProtocolTest {
 private void set(Object target,String name,Object value)throws Exception{Field f=target.getClass().getDeclaredField(name);f.setAccessible(true);f.set(target,value);}
 @Test public void newPositionDrainsCancelledSearchBeforeNewGo()throws Exception{
  PhoneEngine engine=new PhoneEngine();Field q=PhoneEngine.class.getDeclaredField("output");q.setAccessible(true);BlockingQueue<String> output=(BlockingQueue<String>)q.get(engine);List<String> commands=new ArrayList<>();
  Process fake=new Process(){public OutputStream getOutputStream(){return OutputStream.nullOutputStream();}public InputStream getInputStream(){return InputStream.nullInputStream();}public InputStream getErrorStream(){return InputStream.nullInputStream();}public int waitFor(){return 0;}public int exitValue(){throw new IllegalThreadStateException();}public void destroy(){}public boolean isAlive(){return true;}};
  Writer writer=new Writer(){StringBuilder text=new StringBuilder();public void write(char[] c,int a,int n){text.append(c,a,n);}public void close(){}public void flush(){for(String command:text.toString().split("\n")){commands.add(command);if(command.equals("stop"))output.offer("bestmove e2e4");if(command.equals("isready"))output.offer("readyok");if(command.startsWith("go ")){output.offer("info depth 9 score cp 32 pv e7e5 g1f3");output.offer("bestmove e7e5");}}text.setLength(0);}};
  set(engine,"process",fake);set(engine,"input",new BufferedWriter(writer));set(engine,"searching",true);
  PhoneSettings settings=new PhoneSettings(RuntimeEnvironment.getApplication(),"protocol-test");settings.p.edit().clear().putFloat("seconds",.2f).apply();ChessPosition board=new ChessPosition("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1");PhoneEngine.Result result=engine.search(RuntimeEnvironment.getApplication(),board,settings,false,null);
  assertEquals("e7e5",result.lines().get(0).move());assertEquals(Integer.valueOf(-32),result.lines().get(0).cp());assertEquals("stop",commands.get(0));assertTrue(commands.contains("go movetime 200 depth 18"));assertTrue(commands.contains("setoption name Threads value 1"));
   settings.p.edit().putString("mode","Adaptive").putFloat("seconds",.5f).putInt("depth",40).apply();
   engine.search(RuntimeEnvironment.getApplication(),board,settings,false,null);
   assertTrue(commands.contains("go movetime 286 depth 10"));
 }

 @Test public void lockedSuggestionsGrowFromOneToFourAndKeepTheirReplies() {
   PhoneEngine.Line e4 = new PhoneEngine.Line("e2e4", 20, null, 4, List.of("e2e4"));
   PhoneEngine.Line e4WithReply = new PhoneEngine.Line("e2e4", 40, null, 14, List.of("e2e4", "e7e5"));
   PhoneEngine.Line d4 = new PhoneEngine.Line("d2d4", 50, null, 14, List.of("d2d4", "d7d5"));
   PhoneEngine.Line nf3 = new PhoneEngine.Line("g1f3", 10, null, 14, List.of("g1f3"));
   PhoneEngine.Line c4 = new PhoneEngine.Line("c2c4", 5, null, 14, List.of("c2c4"));
   PhoneEngine.Result early = new PhoneEngine.Result("same-position", "test", List.of(e4));
   PhoneEngine.Result complete = new PhoneEngine.Result("same-position", "test", List.of(d4, e4WithReply, nf3, c4));
   PhoneEngine.Result locked = PhoneEngine.lockSuggestions(early, complete, 4);
   assertEquals(List.of("e2e4", "d2d4", "g1f3", "c2c4"),
       locked.lines().stream().map(PhoneEngine.Line::move).toList());
   assertEquals(e4WithReply.pv(), locked.lines().get(0).pv());
   assertEquals(e4.cp(), locked.lines().get(0).cp());
   PhoneEngine.Result moved = new PhoneEngine.Result("new-position", "test", List.of(d4));
   assertSame(moved, PhoneEngine.lockSuggestions(locked, moved, 4));
 }
}
