package app.boardlens.companion;
import android.graphics.*;
import android.os.SystemClock;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.*;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;
import java.util.function.Consumer;
/** Throttled, bundled on-device OCR for visible result banners. Never queues frames. */
final class ResultWatcher implements AutoCloseable {
  private final TextRecognizer reader=TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);
  private volatile boolean busy,closed;private long next;
  boolean due(){return !closed&&!busy&&SystemClock.elapsedRealtime()>=next;}
  void offer(Bitmap frame,Rect board,Consumer<String> result){
    if(board==null||!due())return;next=SystemClock.elapsedRealtime()+1000;busy=true;
    int margin=board.width()/3;Rect r=new Rect(Math.max(0,board.left-margin),Math.max(0,board.top-margin),Math.min(frame.getWidth(),board.right+margin),Math.min(frame.getHeight(),board.bottom+margin));
    Bitmap crop=Bitmap.createBitmap(frame,r.left,r.top,r.width(),r.height()),image;
    float scale=Math.min(1,1000f/Math.max(crop.getWidth(),crop.getHeight()));
    image=Bitmap.createScaledBitmap(crop,Math.max(1,Math.round(crop.getWidth()*scale)),Math.max(1,Math.round(crop.getHeight()*scale)),true);
    if(image==frame)image=frame.copy(Bitmap.Config.ARGB_8888,false);if(crop!=frame&&crop!=image)crop.recycle();
    final Bitmap owned=image;
    reader.process(InputImage.fromBitmap(owned,0)).addOnSuccessListener(Runnable::run,text->{ScreenService.resultCheck="No visible result";if(!closed)for(Text.TextBlock block:text.getTextBlocks())for(Text.Line line:block.getLines()){String reason=GameEndText.reason(line.getText());if(reason!=null){ScreenService.resultCheck="Visible result found";result.accept(reason);return;}}}).addOnFailureListener(Runnable::run,error->{ScreenService.resultCheck="Result check: "+error.getClass().getSimpleName();}).addOnCompleteListener(Runnable::run,task->{owned.recycle();busy=false;});
  }
  public void close(){closed=true;reader.close();}
}
