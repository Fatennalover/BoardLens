package app.boardlens.companion;

import android.content.Context;
import android.graphics.*;
import java.util.*;
import org.json.*;

/** Reads several rank labels, never a single pawn/king location, to override orientation. */
final class RankLabels {
  private final List<float[]>[] bank;
  @SuppressWarnings("unchecked") RankLabels(Context context)throws Exception{
    bank=new List[8];JSONObject json;
    try(var in=context.getAssets().open("models/rank-labels.json")){json=new JSONObject(new String(Streams.read(in,1000000),java.nio.charset.StandardCharsets.UTF_8));}
    for(int n=0;n<8;n++){bank[n]=new ArrayList<>();JSONArray items=json.getJSONArray(""+(n+1));for(int k=0;k<items.length();k++){JSONArray a=items.getJSONArray(k);float[] mask=new float[384];for(int j=0;j<384;j++)mask[j]=a.getInt(j)/255f;bank[n].add(mask);}}
  }
  Boolean read(Bitmap image,Rect r){
    float cell=r.width()/8f;if(cell<20||Math.abs(r.height()-r.width())>cell*.1)return null;
    int white=0,black=0;
    for(int row=0;row<8;row++){
      int x0=r.left+Math.round(cell*.015f),y0=r.top+Math.round((row+.015f)*cell),w=Math.round(cell*.25f)-Math.round(cell*.015f),h=Math.round((row+.29f)*cell)-Math.round((row+.015f)*cell);
      if(x0<0||y0<0||x0+w>image.getWidth()||y0+h>image.getHeight())return null;
      int[] p=new int[w*h];image.getPixels(p,0,w,x0,y0,w,h);int[] rr=new int[p.length],gg=rr.clone(),bb=rr.clone();
      for(int i=0;i<p.length;i++){rr[i]=Color.red(p[i]);gg[i]=Color.green(p[i]);bb[i]=Color.blue(p[i]);}Arrays.sort(rr);Arrays.sort(gg);Arrays.sort(bb);int red=rr[p.length/2],green=gg[p.length/2],blue=bb[p.length/2];
      boolean[] mask=new boolean[p.length];for(int i=0;i<p.length;i++){int a=Color.red(p[i])-red,b=Color.green(p[i])-green,c=Color.blue(p[i])-blue;mask[i]=a*a+b*b+c*c>1225;}
      int[] labels=new int[p.length],queue=new int[p.length];int label=0;float best=1,forward=1,reverse=1;
      for(int i=0;i<p.length;i++)if(mask[i]&&labels[i]==0){
        int head=0,tail=1,minX=w,minY=h,maxX=0,maxY=0;queue[0]=i;labels[i]=++label;
        while(head<tail){int at=queue[head++],x=at%w,y=at/w;minX=Math.min(x,minX);maxX=Math.max(x,maxX);minY=Math.min(y,minY);maxY=Math.max(y,maxY);
          for(int dy=-1;dy<=1;dy++)for(int dx=-1;dx<=1;dx++){int xx=x+dx,yy=y+dy;if(xx<0||yy<0||xx>=w||yy>=h)continue;int v=yy*w+xx;if(mask[v]&&labels[v]==0){labels[v]=label;queue[tail++]=v;}}
        }
        int cw=maxX-minX+1,ch=maxY-minY+1;if(cw<cell*.025||cw>cell*.18||ch<cell*.07||ch>cell*.25||tail<5)continue;
        float[] glyph=new float[384];
        for(int y=0;y<24;y++)for(int x=0;x<16;x++){
          // Area samples keep small anti-aliased glyphs comparable at different screen scales.
          float sum=0,area=0;double ax=x*cw/16.,bx=(x+1)*cw/16.,ay=y*ch/24.,by=(y+1)*ch/24.;
          for(int yy=(int)ay;yy<Math.ceil(by);yy++)for(int xx=(int)ax;xx<Math.ceil(bx);xx++){float weight=(float)((Math.min(xx+1,bx)-Math.max(xx,ax))*(Math.min(yy+1,by)-Math.max(yy,ay)));area+=weight;if(labels[(yy+minY)*w+xx+minX]==label)sum+=weight;}glyph[y*16+x]=sum/area;
        }
        float a=score(glyph,7-row),b=score(glyph,row);if(Math.min(a,b)<best){best=Math.min(a,b);forward=a;reverse=b;}
      }
      if(best<.18){if(forward+.035<reverse)white++;if(reverse+.035<forward)black++;}
    }
    return white>=4&&white-black>=3?Boolean.TRUE:black>=4&&black-white>=3?Boolean.FALSE:null;
  }
  private float score(float[] glyph,int digit){float best=1;for(float[] t:bank[digit]){float sum=0;for(int i=0;i<384;i++){float d=glyph[i]-t[i];sum+=d*d;}best=Math.min(best,sum/384);}return best;}
}
