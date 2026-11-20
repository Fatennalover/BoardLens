package app.boardlens.companion;
import android.app.Application;
import android.graphics.RectF;
import android.view.*;
import org.junit.*;
import org.junit.runner.RunWith;
import org.robolectric.*;
import org.robolectric.annotation.Config;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class) @Config(sdk=35,application=Application.class)
public class FloatingEvaluationTest {
 @Test public void onlyTheSmallPanelReceivesDragAndRestoresClampedPosition(){
  var app=RuntimeEnvironment.getApplication();PhoneSettings prefs=new PhoneSettings(app);prefs.p.edit().clear().commit();
  FloatingEvaluation bar=new FloatingEvaluation(app);
  try{
   bar.show(new OverlayLayout.Box(80,70,248,114,false),360,800,28,24,true,"+0.4",.6f);
   WindowManager.LayoutParams p=(WindowManager.LayoutParams)bar.getLayoutParams();
   assertTrue((p.flags&WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE)!=0);
   assertEquals(0,p.flags&WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE);assertTrue(p.width<360&&p.height<100);
   for(int action:new int[]{MotionEvent.ACTION_DOWN,MotionEvent.ACTION_MOVE,MotionEvent.ACTION_UP}){
    MotionEvent e=MotionEvent.obtain(0,1,action,action==MotionEvent.ACTION_DOWN?100:1000,action==MotionEvent.ACTION_DOWN?80:2000,0);assertTrue(bar.onTouchEvent(e));e.recycle();
   }
   RectF at=bar.bounds();assertTrue(at.right<=360&&at.bottom<=776);assertEquals("Custom",prefs.evaluationPosition());
   bar.hide();bar.show(new OverlayLayout.Box(80,70,248,114,false),360,800,28,24,true,"+0.5",.65f);
   assertEquals(at,bar.bounds());
   bar.show(new OverlayLayout.Box(80,70,248,114,false),800,360,24,24,true,"+0.5",.65f);
   assertTrue(bar.bounds().right<=800&&bar.bounds().bottom<=336);
  }finally{bar.remove();}
 }
}
