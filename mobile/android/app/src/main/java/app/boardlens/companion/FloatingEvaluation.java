package app.boardlens.companion;

import android.animation.ValueAnimator;
import android.content.Context;
import android.graphics.*;
import android.view.*;

/** Only this small panel receives touches; the board-sized arrow window stays passive. */
final class FloatingEvaluation extends View {
  private final WindowManager wm;
  private final PhoneSettings settings;
  private final Paint pen=new Paint(3);
  private WindowManager.LayoutParams params;
  private boolean attached,vertical,whiteBottom;
  private volatile boolean visible,dragging;
  private int screenWidth,screenHeight,safeTop,safeBottom;
  private float downX,downY,originX,originY,share=.5f,target=.5f;
  private String score="…";
  private ValueAnimator animation;
  private volatile RectF bounds;

  FloatingEvaluation(Context context){
    super(context);wm=context.getSystemService(WindowManager.class);settings=new PhoneSettings(context);
    setContentDescription("Evaluation. Drag to move.");setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
  }
  RectF bounds(){return visible?bounds:null;}
  boolean visible(){return visible;}
  boolean dragging(){return dragging;}
  private int gap(){return Math.max(4,Math.round(8*getResources().getDisplayMetrics().density));}

  void show(OverlayLayout.Box box,int width,int height,int topInset,int bottomInset,
      boolean bottom,String label,float value){
    screenWidth=width;screenHeight=height;safeTop=topInset+gap();safeBottom=height-bottomInset-gap();
    whiteBottom=bottom;score=label;
    if(!dragging){
      vertical=box.vertical();int x=box.left(),y=box.top(),w=box.right()-x,h=box.bottom()-y;
      if(settings.evaluationPosition().equals("Custom")){
        x=gap()+Math.round(settings.evaluationX()*Math.max(0,width-w-2*gap()));
        y=safeTop+Math.round(settings.evaluationY()*Math.max(0,safeBottom-safeTop-h));
      }
      if(params==null){
        params=new WindowManager.LayoutParams(w,h,WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE|WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT);
        params.gravity=Gravity.TOP|Gravity.LEFT;params.alpha=.85f;params.setTitle("BoardLens draggable evaluation");
        if(android.os.Build.VERSION.SDK_INT>=28)params.layoutInDisplayCutoutMode=
            android.os.Build.VERSION.SDK_INT>=30?WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS:
                WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
      }
      boolean changed=params.x!=x||params.y!=y||params.width!=w||params.height!=h||!visible;
      params.width=w;params.height=h;params.x=x;params.y=y;clamp();
      if(!attached){wm.addView(this,params);attached=true;}else if(changed)wm.updateViewLayout(this,params);
      visible=true;setVisibility(VISIBLE);updateBounds();
    }
    float next=Math.max(0,Math.min(1,value));
    if(next!=target){
      if(animation!=null)animation.cancel();target=next;
      if(ValueAnimator.areAnimatorsEnabled()){
        animation=ValueAnimator.ofFloat(share,target);animation.setDuration(200);
        animation.addUpdateListener(a->{share=(float)a.getAnimatedValue();invalidate();});animation.start();
      }else share=target;
    }
    invalidate();
  }
  private void clamp(){
    params.x=Math.max(gap(),Math.min(Math.max(gap(),screenWidth-gap()-params.width),params.x));
    params.y=Math.max(safeTop,Math.min(Math.max(safeTop,safeBottom-params.height),params.y));
  }
  private void updateBounds(){bounds=new RectF(params.x,params.y,params.x+params.width,params.y+params.height);}
  @Override public boolean onTouchEvent(MotionEvent e){
    if(params==null||!visible)return false;
    switch(e.getActionMasked()){
      case MotionEvent.ACTION_DOWN:
        dragging=true;downX=e.getRawX();downY=e.getRawY();originX=params.x;originY=params.y;return true;
      case MotionEvent.ACTION_MOVE:
        params.x=Math.round(originX+e.getRawX()-downX);params.y=Math.round(originY+e.getRawY()-downY);
        clamp();wm.updateViewLayout(this,params);updateBounds();return true;
      case MotionEvent.ACTION_UP:
      case MotionEvent.ACTION_CANCEL:
        dragging=false;
        settings.p.edit().putFloat("evaluation_x",(params.x-gap())/(float)Math.max(1,screenWidth-params.width-2*gap()))
            .putFloat("evaluation_y",(params.y-safeTop)/(float)Math.max(1,safeBottom-safeTop-params.height))
            .putBoolean("evaluation_vertical",vertical).putString("evaluation_position","Custom").apply();
        performClick();return true;
      default:return true;
    }
  }
  @Override public boolean performClick(){super.performClick();return true;}
  void hide(){visible=false;dragging=false;setVisibility(INVISIBLE);}
  void remove(){hide();if(animation!=null)animation.cancel();if(attached){try{wm.removeView(this);}catch(IllegalArgumentException ignored){}attached=false;}}
  @Override protected void onDraw(Canvas canvas){
    float d=getResources().getDisplayMetrics().density;RectF r=new RectF(0,0,getWidth(),getHeight());
    pen.setStyle(Paint.Style.FILL);pen.setColor(0xff211932);canvas.drawRoundRect(r,10*d,10*d,pen);
    pen.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));pen.setTextAlign(Paint.Align.CENTER);
    pen.setColor(0xfff0e4ff);pen.setTextSize((vertical?11:14)*d);String text=vertical?score:"W "+score;
    if(pen.measureText(text)>r.width()-16*d)pen.setTextSize(pen.getTextSize()*(r.width()-16*d)/pen.measureText(text));
    canvas.drawText(text,r.centerX(),18*d,pen);
    RectF track=vertical?new RectF(12*d,28*d,r.right-12*d,r.bottom-8*d):new RectF(10*d,28*d,r.right-10*d,r.bottom-9*d);
    pen.setColor(0xff352848);canvas.drawRoundRect(track,4*d,4*d,pen);
    canvas.save();Path clip=new Path();clip.addRoundRect(track,4*d,4*d,Path.Direction.CW);canvas.clipPath(clip);pen.setColor(0xfff4f7f4);
    if(vertical){float h=track.height()*share;canvas.drawRect(track.left,whiteBottom?track.bottom-h:track.top,track.right,whiteBottom?track.bottom:track.top+h,pen);}
    else canvas.drawRect(track.left,track.top,track.left+track.width()*share,track.bottom,pen);
    canvas.restore();pen.setColor(0xff8673a2);
    for(int i=0;i<3;i++)canvas.drawCircle(r.right-6*d,(8+i*4)*d,d,pen);
  }
}
