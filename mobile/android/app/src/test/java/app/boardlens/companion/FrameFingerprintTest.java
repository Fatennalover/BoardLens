package app.boardlens.companion;
import java.nio.ByteBuffer;import org.junit.Test;import static org.junit.Assert.*;
public class FrameFingerprintTest {
 @Test public void rgbaPaddingOffsetAndOverlayMasksMatchBoardSamples(){ByteBuffer b=ByteBuffer.allocate(4+24*2);b.position(4);for(int y=0;y<2;y++)for(int x=0;x<4;x++){int p=4+y*24+x*4;b.put(p,(byte)(10+x));b.put(p+1,(byte)(20+y));b.put(p+2,(byte)30);b.put(p+3,(byte)255);}int[] f=FrameFingerprint.read(b,4,2,24,4,1,0,4,2,(x,y)->x==2);assertEquals(0xff0b141e,f[0]);assertEquals(0,f[48]);assertEquals(0xff0d151e,f[f.length-1]);assertEquals(4,b.position());}
 @Test public void invalidOrTruncatedCaptureFallsBackToNormalRead(){assertNull(FrameFingerprint.read(ByteBuffer.allocate(8),4,2,16,4,0,0,4,2,(x,y)->false));assertNull(FrameFingerprint.read(ByteBuffer.allocate(32),4,2,16,4,-1,0,4,2,(x,y)->false));}
 @Test public void selectionMarksPreserveThePositionButMovingAPieceDoesNot() {
  var board=new ChessPosition("6k1/8/8/8/8/8/4P3/6K1 w - - 0 1");
  int[] before=new int[96*96];
  for(int row=0;row<8;row++)for(int col=0;col<8;col++) {
   int fill=(row+col)%2==0?0xffaaaaaa:0xff777777;
   boolean piece=board.b[(7-row)*8+col]!='.';
   for(int y=0;y<12;y++)for(int x=0;x<12;x++)
    before[(row*12+y)*96+col*12+x]=piece&&x>=4&&x<8&&y>=4&&y<8?0xffeeeeee:fill;
  }
  int[] marked=before.clone();
  marked[54*96+54]=0xffffff00;
  assertTrue(FrameFingerprint.occupiedShapesMatch(before,marked,board,true));
  for(int y=76;y<80;y++)for(int x=52;x<56;x++)marked[y*96+x]=0xffaaaaaa;
  assertFalse(FrameFingerprint.occupiedShapesMatch(before,marked,board,true));
 }
}
