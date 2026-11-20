package app.boardlens.companion;
import android.app.Application;
import android.graphics.*;
import org.junit.*;
import org.junit.runner.RunWith;
import org.robolectric.*;
import org.robolectric.annotation.*;
import static org.junit.Assert.*;
@RunWith(RobolectricTestRunner.class) @Config(sdk=35,application=Application.class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
public class RankLabelsTest {
 @Test public void actualRenderedCoordinatesDetermineBothOrientations()throws Exception{
  RankLabels labels=new RankLabels(RuntimeEnvironment.getApplication());
  for(int size:new int[]{480,640,1328})for(boolean bottom:new boolean[]{true,false}){
   Bitmap image=Bitmap.createBitmap(size,size,Bitmap.Config.ARGB_8888);Canvas c=new Canvas(image);c.drawColor(Color.rgb(130,130,130));Paint p=new Paint(Paint.ANTI_ALIAS_FLAG);p.setColor(Color.rgb(235,235,235));p.setTypeface(Typeface.create("sans-serif",Typeface.BOLD));float cell=size/8f;p.setTextSize(cell*.21f);
   for(int row=0;row<8;row++)c.drawText(""+(bottom?8-row:row+1),cell*.05f,(row+.23f)*cell,p);
   assertEquals("size="+size,Boolean.valueOf(bottom),labels.read(image,new Rect(0,0,size,size)));image.recycle();
  }
 }
 @Test public void absentCoordinatesAbstain()throws Exception{
  Bitmap image=Bitmap.createBitmap(640,640,Bitmap.Config.ARGB_8888);assertNull(new RankLabels(RuntimeEnvironment.getApplication()).read(image,new Rect(0,0,640,640)));image.recycle();
 }
}
