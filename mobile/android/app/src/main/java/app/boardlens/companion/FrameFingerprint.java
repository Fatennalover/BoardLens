package app.boardlens.companion;
import java.nio.ByteBuffer;

/** Samples RGBA capture pixels directly, avoiding full-screen bitmap copies on idle boards. */
final class FrameFingerprint {
 interface Mask { boolean covers(int x,int y); }
 static int[] read(ByteBuffer pixels,int width,int height,int rowStride,int pixelStride,int left,int top,int right,int bottom,Mask mask){
  if(pixelStride<4||left<0||top<0||right>width||bottom>height||right<=left||bottom<=top)return null;
  int base=pixels.position();long last=base+(long)(bottom-1)*rowStride+(long)(right-1)*pixelStride+4;if(last>pixels.limit())return null;
  int[] result=new int[96*96];
  for(int y=0;y<96;y++)for(int x=0;x<96;x++){
   int xx=left+(int)((x+.5f)*(right-left)/96),yy=top+(int)((y+.5f)*(bottom-top)/96),i=y*96+x;
   if(mask.covers(xx,yy)){result[i]=0;continue;}int at=base+yy*rowStride+xx*pixelStride;
   result[i]=((pixels.get(at+3)&255)<<24)|((pixels.get(at)&255)<<16)|((pixels.get(at+1)&255)<<8)|(pixels.get(at+2)&255);
  }return result;
 }

 static boolean occupiedShapesMatch(int[] before, int[] after, ChessPosition position, boolean whiteBottom) {
  if (before == null || after == null || before.length != 96*96 || after.length != 96*96) return false;
  for (int row=0;row<8;row++) for (int col=0;col<8;col++) {
   int square = whiteBottom ? (7-row)*8+col : row*8+7-col;
   if (position.b[square] == '.') continue;
   int start=row*12*96+col*12;
   int baseBefore=background(before,start), baseAfter=background(after,start);
   int ink=0, matching=0;
   for (int y=2;y<10;y++) for (int x=2;x<10;x++) {
    int index=start+y*96+x;
    if (before[index]==0 || after[index]==0) continue;
    int reference=luma(before[index])-baseBefore;
    if (Math.abs(reference)<30) continue;
    ink++;
    if (Math.abs(reference-(luma(after[index])-baseAfter))<32) matching++;
   }
   if (ink<6 || matching*100<ink*76) return false;
  }
  return true;
 }

 private static int background(int[] pixels,int start) {
  int[] corners={luma(pixels[start+97]),luma(pixels[start+106]),
      luma(pixels[start+961]),luma(pixels[start+970])};
  java.util.Arrays.sort(corners);
  return (corners[1]+corners[2])/2;
 }

 private static int luma(int color) {
  return (77*((color>>16)&255) + 150*((color>>8)&255) + 29*(color&255)) >> 8;
 }
}
