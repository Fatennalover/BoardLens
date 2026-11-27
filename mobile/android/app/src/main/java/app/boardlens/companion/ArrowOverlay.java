package app.boardlens.companion;

import android.content.Context;
import android.graphics.*;
import android.view.*;
import java.util.*;

/** One passive window: never receives taps or keyboard focus. */
final class ArrowOverlay extends View {
  private final WindowManager wm;
  private boolean attached;
  private volatile Rect board;
  private volatile BoardGeometry projection;
  private volatile boolean bottom = true;
  private volatile float[] segments = new float[0];
  private boolean[] narrow = new boolean[0];
  private boolean evaluationVisible;private String score="…",evaluationPosition="Auto";private volatile RectF evaluationBounds;
  private final Paint pen = new Paint(3);
  private List<Integer> customColors=List.of();
  private List<Integer> predictionPlies=List.of();
  private final int[] colors = {0xffffd16c, 0xff51d9da, 0xffb0a4ff};
  private final FloatingEvaluation floating;
  private float evaluationTarget=.5f;

  ArrowOverlay(Context c) {
    super(c);
    wm = (WindowManager) c.getSystemService(Context.WINDOW_SERVICE);
    floating = new FloatingEvaluation(c);
    setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
  }

  void show(Rect rect, boolean whiteBottom, List<String> arrows) {
    show(BoardGeometry.rectangle(rect.left,rect.top,rect.right,rect.bottom),whiteBottom,arrows);
  }

  void show(BoardGeometry geometry,boolean whiteBottom,List<String> arrows){show(geometry,whiteBottom,arrows,false,"…",.5f,"Auto");}
  void show(BoardGeometry geometry,boolean whiteBottom,List<String> arrows,boolean showEvaluation,String label,float share,String placement){
    show(geometry,whiteBottom,arrows,List.of(),showEvaluation,label,share,placement);
  }
  void show(BoardGeometry geometry,boolean whiteBottom,List<String> arrows,List<Integer> arrowColors,boolean showEvaluation,String label,float share,String placement){
    show(geometry, whiteBottom, arrows, arrowColors, List.of(), showEvaluation, label, share, placement);
  }
  void show(BoardGeometry geometry,boolean whiteBottom,List<String> arrows,List<Integer> arrowColors,
            List<Integer> plies,boolean showEvaluation,String label,float share,String placement){
    customColors=List.copyOf(arrowColors);
    predictionPlies=List.copyOf(plies);
    evaluationVisible=showEvaluation;score=label;evaluationPosition=placement;
    evaluationTarget=Math.max(0,Math.min(1,share));

    if(!android.provider.Settings.canDrawOverlays(getContext())){clear();remove();return;}
    projection=geometry;double[] bounds=geometry.bounds();
    board=new Rect((int)bounds[0],(int)bounds[1],(int)Math.ceil(bounds[2]),(int)Math.ceil(bounds[3]));
    bottom = whiteBottom;
    float[] arrowSegments = new float[arrows.size() * 4];
    narrow = new boolean[arrows.size()];
    Map<String, Integer> totals = new HashMap<>();
    Map<String, Integer> indexes = new HashMap<>();
    List<String> paths = new ArrayList<>();
    for (String move : arrows) {
      String path = move.substring(0, 4);
      paths.add(path);
      totals.put(path, totals.getOrDefault(path, 0) + 1);
    }
    for (int i = 0; i < paths.size(); i++) {
      String path = paths.get(i);
      PointF a = point(path.substring(0, 2)), b = point(path.substring(2, 4));
      int count = totals.get(path);
      int lane = indexes.getOrDefault(path, 0);
      indexes.put(path, lane + 1);
      narrow[i] = count > 1;
      float dx = b.x - a.x, dy = b.y - a.y;
      float spacing = (float) (board.width() / 8f * Math.min(.13, .4 / count));
      float offset = (lane - (count - 1) / 2f) * spacing / Math.max(1f, (float) Math.hypot(dx, dy));
      arrowSegments[i * 4] = a.x - dy * offset;
      arrowSegments[i * 4 + 1] = a.y + dx * offset;
      arrowSegments[i * 4 + 2] = b.x - dy * offset;
      arrowSegments[i * 4 + 3] = b.y + dx * offset;
    }
    segments = arrowSegments;
    if (!showEvaluation) floating.hide();
    if (!attached) {
      WindowManager.LayoutParams p =
          new WindowManager.LayoutParams(
              -1,
              -1,
              WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
              WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                  | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                  | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
              PixelFormat.TRANSLUCENT);
      p.gravity = Gravity.TOP | Gravity.LEFT;
      p.alpha = .65f;
      if(android.os.Build.VERSION.SDK_INT>=28)p.layoutInDisplayCutoutMode =
          android.os.Build.VERSION.SDK_INT >= 30
              ? WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS
              : WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
      p.setTitle("BoardLens move arrows");
      try{wm.addView(this, p);attached = true;}
      catch(SecurityException|WindowManager.BadTokenException denied){
        clear();ScreenService.diagnostic="Overlay permission unavailable · enable Display over other apps";return;
      }
    }
    post(this::updateEvaluation);
    invalidate();
  }

  void clear() {
    segments = new float[0];evaluationVisible=false;evaluationBounds=null;floating.hide();
    invalidate();
  }

  boolean evaluationDragging(){return floating.dragging();}
  boolean hasEvaluation(){return evaluationVisible;}
  boolean hasContent(){return hasArrows()||evaluationVisible;}

  boolean hasArrows() {
    return segments.length > 0;
  }

  void remove() {
    floating.remove();
    if (attached) {
      try{wm.removeView(this);}catch(IllegalArgumentException ignored){}finally{attached=false;}
    }
  }

  boolean covers(int x, int y) {
    RectF panel=floating.bounds();if(evaluationVisible&&panel!=null&&panel.contains(x,y))return true;
    Rect r = board;
    if (r == null) return false;
    float cell = r.width() / 8f;
    float[] g = segments;
    for (int i = 0; i < g.length; i += 4) {
      float ax = g[i],
          ay = g[i + 1],
          bx = g[i + 2],
          by = g[i + 3],
          dx = bx - ax,
          dy = by - ay,
          len = dx * dx + dy * dy,
          t = Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / Math.max(1, len)));
      float shaftX = x - ax - t * dx, shaftY = y - ay - t * dy;
      float tipX = x - bx, tipY = y - by;
      if (shaftX * shaftX + shaftY * shaftY < cell * cell * .0064f
          || tipX * tipX + tipY * tipY < cell * cell * .0784f) return true;
    }
    return false;
  }

  private PointF point(String square) {
    double[] point=projection.square(square,bottom);return new PointF((float)point[0],(float)point[1]);
  }

  @Override
  protected void onDraw(Canvas canvas) {
    super.onDraw(canvas);
    if (board == null) return;
    int[] location = new int[2];
    getLocationOnScreen(location);
    canvas.save();
    canvas.translate(-location[0], -location[1]);
    float cell = board.width() / 8f;
    float[] current = segments;
    Map<Integer, RectF> badges = new LinkedHashMap<>();
    for (int i = 0; i < current.length / 4; i++) {
      float ax = current[4 * i], ay = current[4 * i + 1], bx = current[4 * i + 2], by = current[4 * i + 3];
      double angle = Math.atan2(by - ay, bx - ax);
      float head = cell * .28f;
      double spread = narrow[i] ? .22 : .6;
      float tailX = bx - (float) Math.cos(angle) * head * .6f;
      float tailY = by - (float) Math.sin(angle) * head * .6f;
      pen.setColor(i < customColors.size() ? customColors.get(i) : colors[i % colors.length]);
      pen.setStrokeWidth(cell * (narrow[i] ? .056f : .10f));
      pen.setStrokeCap(Paint.Cap.ROUND);
      boolean numbered = i < predictionPlies.size() && predictionPlies.get(i) > 0;
      if (numbered) {
        float dash = Math.max(3, cell * .16f);
        pen.setPathEffect(new DashPathEffect(new float[]{dash, dash * .6f}, 0));
      }
      canvas.drawLine(ax, ay, tailX, tailY, pen);
      pen.setPathEffect(null);
      if (numbered) {
        int ply = predictionPlies.get(i);
        float height = Math.max(15, cell * .36f), width = ply < 10 ? height : height * 1.35f;
        for (float t : new float[]{.56f, .40f, .72f, .25f, .83f}) {
          float x = ax + (bx - ax) * t, y = ay + (by - ay) * t;
          RectF box = new RectF(x - width / 2, y - height / 2, x + width / 2, y + height / 2);
          if (badges.values().stream().noneMatch(other -> RectF.intersects(other, box)) || t == .83f) {
            badges.put(ply, box);
            break;
          }
        }
      }
      Path p = new Path();
      p.moveTo(bx, by);
      p.lineTo(bx - (float) Math.cos(angle - spread) * head, by - (float) Math.sin(angle - spread) * head);
      p.lineTo(bx - (float) Math.cos(angle + spread) * head, by - (float) Math.sin(angle + spread) * head);
      p.close();
      pen.setStyle(Paint.Style.FILL);
      canvas.drawPath(p, pen);
    }

    for (var badge : badges.entrySet()) {
      RectF box = badge.getValue();
      pen.setColor(0xff152630);
      canvas.drawRoundRect(box, box.height() * .22f, box.height() * .22f, pen);
      pen.setColor(Color.WHITE);
      pen.setTextSize(box.height() * .76f);
      pen.setTypeface(Typeface.DEFAULT_BOLD);
      pen.setTextAlign(Paint.Align.CENTER);
      float baseline = box.centerY() - (pen.ascent() + pen.descent()) / 2;
      canvas.drawText(Integer.toString(badge.getKey()), box.centerX(), baseline, pen);
    }
    canvas.restore();
  }
  @Override protected void onSizeChanged(int w,int h,int oldw,int oldh){super.onSizeChanged(w,h,oldw,oldh);updateEvaluation();}
  private void updateEvaluation(){
    if(!evaluationVisible||projection==null||getWidth()==0||getHeight()==0){floating.hide();return;}
    float d=getResources().getDisplayMetrics().density;WindowInsets insets=getRootWindowInsets();
    int top=insets==null?0:insets.getStableInsetTop(),bottomInset=insets==null?0:insets.getStableInsetBottom();
    PhoneSettings prefs=new PhoneSettings(getContext());String mode=evaluationPosition;
    if(mode.equals("Custom"))mode=prefs.evaluationVertical()?"Left":"Top";
    OverlayLayout.Box box=OverlayLayout.place(projection.bounds(),getWidth(),getHeight(),d,top,bottomInset,mode);
    try{floating.show(box,getWidth(),getHeight(),top,bottomInset,bottom,score,evaluationTarget);}
    catch(SecurityException|WindowManager.BadTokenException denied){evaluationVisible=false;floating.hide();ScreenService.diagnostic="Overlay permission unavailable";}
  }
}
