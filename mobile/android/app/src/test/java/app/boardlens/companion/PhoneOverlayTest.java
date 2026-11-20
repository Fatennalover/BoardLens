package app.boardlens.companion;
import android.app.Application;import android.graphics.*;import android.view.*;import org.junit.*;import org.junit.runner.RunWith;import org.robolectric.*;import org.robolectric.annotation.*;import org.robolectric.shadows.ShadowSettings;import java.io.*;import java.util.*;import static org.junit.Assert.*;
@RunWith(RobolectricTestRunner.class) @Config(sdk=35,application=Application.class) @GraphicsMode(GraphicsMode.Mode.NATIVE)
public class PhoneOverlayTest {
 @Test public void evaluationAloneDrawsWithoutInterceptingBoardTouches()throws Exception{
  var app=RuntimeEnvironment.getApplication();ShadowSettings.setCanDrawOverlays(true);ArrowOverlay overlay=new ArrowOverlay(app);overlay.show(BoardGeometry.rectangle(0,150,360,510),true,Collections.emptyList(),true,"+0.31",.7f,"Auto");overlay.measure(View.MeasureSpec.makeMeasureSpec(360,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(800,View.MeasureSpec.EXACTLY));overlay.layout(0,0,360,800);
  Bitmap image=Bitmap.createBitmap(360,800,Bitmap.Config.ARGB_8888);Canvas canvas=new Canvas(image);canvas.drawColor(0xff182229);try(InputStream in=app.getAssets().open("fixtures/fen2image-italian.png")){Bitmap board=BitmapFactory.decodeStream(in);canvas.drawBitmap(board,null,new Rect(0,150,360,510),null);board.recycle();}overlay.draw(canvas);assertTrue(overlay.hasEvaluation());assertFalse(overlay.hasArrows());assertTrue(overlay.covers(180,120));WindowManager.LayoutParams p=(WindowManager.LayoutParams)overlay.getLayoutParams();assertTrue((p.flags&WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE)!=0);assertTrue((p.flags&WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE)!=0);assertEquals(.65f,p.alpha,.001);
  File folder=new File("build/reports/mobile-previews");folder.mkdirs();try(FileOutputStream out=new FileOutputStream(new File(folder,"phone-eval-overlay.png"))){image.compress(Bitmap.CompressFormat.PNG,100,out);}overlay.clear();assertFalse(overlay.hasContent());overlay.remove();
 }
 @Test public void agreeingEnginesKeepColorsOnSeparateLanes(){
  var app=RuntimeEnvironment.getApplication();
  ShadowSettings.setCanDrawOverlays(true);
  ArrowOverlay overlay=new ArrowOverlay(app);
  try{
   overlay.show(BoardGeometry.rectangle(0,150,400,550),true,List.of("d2d4","d2d4","d2d4"),
       List.of(0xffffc65c,0xffec8be9,0xff83e4bb),false,"",.5f,"Auto");
   overlay.measure(View.MeasureSpec.makeMeasureSpec(400,View.MeasureSpec.EXACTLY),View.MeasureSpec.makeMeasureSpec(750,View.MeasureSpec.EXACTLY));
   overlay.layout(0,0,400,750);
   Bitmap pixels=Bitmap.createBitmap(400,750,Bitmap.Config.ARGB_8888);
   overlay.draw(new Canvas(pixels));
   Set<Integer> colors=new HashSet<>();
   for(int x=160;x<191;x++){
    int color=pixels.getPixel(x,465);
    if(Color.alpha(color)>240) colors.add(color);
   }
   assertTrue(colors.containsAll(List.of(0xffffc65c,0xffec8be9,0xff83e4bb)));
   assertTrue(overlay.covers(175,465));
   pixels.recycle();
  }finally{overlay.remove();}
 }
 @Test public void fastDiscoveryFindsBoardsInExistingScreenFixtures()throws Exception{
  var app=RuntimeEnvironment.getApplication();for(String name:new String[]{"chesscom-italian-white.png","lichess-italian-black.png","native-landscape.png"})try(InputStream in=app.getAssets().open("fixtures/"+name)){Bitmap image=BitmapFactory.decodeStream(in);long start=System.nanoTime();var boxes=GradientBoards.detectFast(image);System.out.println(name+" fast discovery "+((System.nanoTime()-start)/1000000)+" ms · "+boxes.size()+" candidates");assertFalse(name,boxes.isEmpty());image.recycle();}
 }
}
