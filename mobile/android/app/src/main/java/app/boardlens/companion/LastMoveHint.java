package app.boardlens.companion;

import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.Rect;
import java.util.Arrays;

/** Infers a turn only when two contrasting square highlights include one piece. */
final class LastMoveHint {
  static Boolean read(Bitmap image, Rect box, String placement, boolean whiteBottom) {
    if (Math.abs(box.width()-box.height()) > box.width()/20) return null;
    ChessPosition board = new ChessPosition(placement);
    int[][] square = new int[64][3];
    int[][][] sample = new int[2][3][32];
    int[] parityCount = new int[2];
    float[] offsets = {.11f,.87f};
    for (int i=0;i<64;i++) {
      int row=i/8,col=i%8,parity=(row+col)%2;
      int[][] corners=new int[3][4];
      int n=0;
      for(float y:offsets)for(float x:offsets){
        int color=image.getPixel(box.left+(int)((col+x)*box.width()/8),box.top+(int)((row+y)*box.height()/8));
        corners[0][n]=Color.red(color);
        corners[1][n]=Color.green(color);
        corners[2][n++]=Color.blue(color);
      }
      for(int c=0;c<3;c++){
        Arrays.sort(corners[c]);
        sample[parity][c][parityCount[parity]]=square[i][c]=(corners[c][1]+corners[c][2])/2;
      }
      parityCount[parity]++;
    }
    for(int[][] group:sample)for(int[] channel:group)Arrays.sort(channel);
    int count=0;
    Character moved=null;
    for(int i=0;i<64;i++){
      int p=(i/8+i%8)%2,error=0;
      for(int c=0;c<3;c++){
        int d=square[i][c]-sample[p][c][16];
        error+=d*d;
      }
      if(error<45*45)continue;
      if(++count>2)return null;
      int index=whiteBottom?(7-i/8)*8+i%8:(i/8)*8+7-i%8;
      char piece=board.b[index];
      if(piece!='.'){
        if(moved!=null)return null;
        moved=piece;
      }
    }
    return count==2&&moved!=null ? !Character.isUpperCase(moved) : null;
  }
}
