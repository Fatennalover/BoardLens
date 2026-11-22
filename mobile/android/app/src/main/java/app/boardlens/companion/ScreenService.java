package app.boardlens.companion;

import android.app.*;
import android.content.*;
import android.content.pm.ServiceInfo;
import android.graphics.*;
import android.hardware.display.*;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.*;
import android.os.*;
import android.util.DisplayMetrics;
import android.view.WindowManager;
import java.util.*;
import java.util.concurrent.*;

/**
 * Explicit, user-started capture. No boot receiver, accessibility service, recording or uploads.
 */
public final class ScreenService extends Service {
  static final String OPEN_FLOATING_EXTRA = "open_floating_menu";
  static volatile long frames = 0, reads = 0;
  static volatile long lastFrameAt, lastBoardAt;
  static volatile int captureWidth, captureHeight;
  static volatile String scanStage="Stopped";
  static volatile String diagnostic = "";
  static volatile String resultCheck="Not checked";
  static volatile boolean running = false, phoneVisible = false;
  static volatile String status = "Stopped",
      fen = "",
      suggestion = "Waiting for a board",
      evaluation = "—";
  static volatile Bitmap preview;
  static volatile ChessPosition trackedPosition;
  static volatile boolean trackedWhiteBottom = true;
  record PracticeSnapshot(ChessPosition position, boolean whiteBottom) {}
  static volatile PracticeSnapshot lastScannedBoard;
  static volatile float whiteShare = .5f;
  static volatile boolean hasEvaluationValue;
  private static volatile String evaluationBadge="…";
  static volatile Runnable listener;
  private static volatile ScreenService active;

  static void setPhoneVisible(boolean visible) {
    phoneVisible = visible;
    ScreenService s = active;
    if (visible && s != null)
      s.main.post(
          () -> {
            if (s.overlay != null) s.overlay.clear();
            s.syncFloatingControls();

          });
    if(!visible&&s!=null&&s.capture!=null){s.capture.post(s::requestTick);s.main.post(s::syncFloatingControls);}
  }

  static void openFloatingMenu() {
    ScreenService service = active;
    if (service != null && service.floatingControls != null) service.floatingControls.open();
  }

  static void changed() {
    Runnable r = listener;
    if (r != null) new Handler(Looper.getMainLooper()).post(r);
  }

  private final Handler main = new Handler(Looper.getMainLooper());
  private HandlerThread captureThread;
  private Handler capture;
  private MediaProjection projection;
  private volatile boolean terminating;
  private VirtualDisplay display;
  private ImageReader images;
  private BoardReader reader;
  private ResultWatcher resultWatcher;
  private Rect resultTarget;private volatile long resultRevision;
  private Bitmap cachedFrame;
  private Bitmap searchedFrame;
  private String searchedSettings="";
  private final FramePixels framePixels=new FramePixels();
  private ArrowOverlay overlay;
  private FloatingControls floatingControls;
  private boolean controlsOccluding;
  private Rect controlsBoard;
  private volatile long controlsMovedAt;
  private PhoneSettings settings;
  private volatile boolean gameEnded;
  private boolean turnKnown;
  private String gameEndReason="";
  static void visibleGameEnd(String reason){ScreenService s=active;if(s==null||s.capture==null)return;s.capture.post(()->{if(!running||s.position==null||(s.target==null&&SystemClock.elapsedRealtime()-lastBoardAt>8000)||phoneVisible)return;s.gameEnded=true;s.gameEndReason=reason;s.generation.incrementAndGet();s.moves.cancel();s.evaluator.cancel();s.extraEngines.cancel();s.lastArrows=Collections.emptyList();status="Game over · "+reason;suggestion="Game ended";s.main.post(()->s.overlay.clear());s.notifyStatus(status);changed();});}

  private final android.content.SharedPreferences.OnSharedPreferenceChangeListener preferenceListener=(p,key)->preferenceChanged(key);
  private volatile Rect target;
  private BoardGeometry targetGeometry;
  private ChessPosition position;
  private boolean allowPositionReset = true;
  private long targetLostAt=-1;
  private boolean bottom = true;
  private String lastSettings = "", lastTurn = "Auto",lastOrientation="Auto";
  private int failures = 0;
  private final ReadConfirmation<BoardReader.Read> confirmation=new ReadConfirmation<>();
  private final Runnable tickTask=this::tick;private long lastTick;
  private long modelRevision;private final Runnable settingsTask=this::applyCurrentSettings;
  private final android.content.SharedPreferences.OnSharedPreferenceChangeListener modelListener=(p,key)->modelReady(key);
  private long lastScan = 0;
  private final java.util.concurrent.atomic.AtomicLong generation = new java.util.concurrent.atomic.AtomicLong();
  private boolean cleanFrame = false;
  private volatile boolean needsRead=true;
  private volatile int[] baseline;
  private long blankSince=-1;
  private String notificationText="Scan now to refresh · Stop to end sharing";
  private volatile List<String> lastArrows = Collections.emptyList();
  private final ArrowEngines extraEngines=new ArrowEngines();
  private volatile List<Integer> lastArrowColors=List.of();
  private final LocalEngines moves = new LocalEngines(), evaluator = new LocalEngines();
  private final LatestWorkQueue moveWorker = new LatestWorkQueue("BoardLens-moves"),
      evalWorker = new LatestWorkQueue("BoardLens-evaluation");

  private void preferenceChanged(String key){
    if (FloatingControls.BROWSER_ENABLED.equals(key)) return;
    if (FloatingControls.ENABLED.equals(key)) { main.post(this::syncFloatingControls); return; }
    if (ArrowEngines.isColorKey(key)) { renderOverlay(); return; }
    if (ArrowEngines.PREF.equals(key)) {
      if (capture != null) {
        capture.removeCallbacks(extraSettingsTask);
        capture.postDelayed(extraSettingsTask, 80);
      }
      return;
    }
    if("arrows".equals(key)||"screen_evaluation".equals(key)||"evaluation_position".equals(key)||"evaluation_x".equals(key)||"evaluation_y".equals(key)||"evaluation_vertical".equals(key)){renderOverlay();changed();return;}
    if("evaluation_enabled".equals(key)&&!settings.evaluationEnabled()){evaluator.cancel();evalWorker.submit(evaluator::close);evaluation="Evaluation off";evaluationBadge="Off";renderOverlay();changed();}
    if(capture!=null){capture.removeCallbacks(settingsTask);capture.postDelayed(settingsTask,80);}
  }
  void modelReady(String key){
    if(settings==null||capture==null)return;
    EngineCatalog.Entry primary=EngineCatalog.get(settings.engine()),eval=EngineCatalog.get(settings.evaluator());
    boolean stockfish="verified".equals(key)&&(primary.kind().equals("stockfish")||settings.evaluationEnabled()&&eval.kind().equals("stockfish"));
    boolean primaryChanged = stockfish || primary.id().equals(key)
        || settings.evaluationEnabled() && eval.id().equals(key);
    if (primaryChanged) capture.post(() -> {modelRevision++;applyCurrentSettings();});
    else if (extraEngines.installsFor(settings, key)) capture.post(extraSettingsTask);
  }
  private final Runnable extraSettingsTask = () -> {
    if (!running || gameEnded || position == null || target == null) return;
    extraEngines.request(this, position, settings.snapshot(), capture, this::renderOverlay);
    renderOverlay();
  };
  void applyCurrentSettings(){
    if(!running||settings==null)return;
    String key=settingsKey();if(key.equals(lastSettings))return;
    lastSettings=key;
    if(!settings.turn().equals(lastTurn)||!settings.orientation().equals(lastOrientation)){
      if(!settings.turn().equals(lastTurn)&&!settings.turn().equals("Auto"))position=null;
      lastTurn=settings.turn();lastOrientation=settings.orientation();baseline=null;confirmation.clear();needsRead=true;requestTick();return;
    }
    if(position!=null&&target!=null){
      lastAnalyzedSettings=key;pinned=null;displayedFen="";displayedMove="";lastArrows=Collections.emptyList();
      analyze(position,new Rect(target),bottom);
    }
  }


  @Override
  public IBinder onBind(Intent i) {
    return null;
  }

  @Override
  public int onStartCommand(Intent intent, int flags, int id) {
    if (intent == null || "STOP".equals(intent.getAction())) {

      stopSelf();
      return START_NOT_STICKY;
    }
    if ("FLOATING_CONTROLS".equals(intent.getAction())) {
      if (running && floatingControls != null) floatingControls.toggle();
      return START_NOT_STICKY;
    }
    if ("REFRESH".equals(intent.getAction())) {
      refreshScreen();
      return START_NOT_STICKY;
    }
    if (running) return START_NOT_STICKY;
    try {
      active = this;
      frames=reads=lastFrameAt=lastBoardAt=0;captureWidth=captureHeight=0;
      scanStage="Starting capture";diagnostic="";fen="";preview=null;trackedPosition=null;suggestion="Waiting for a board";
      settings = new PhoneSettings(this);
      settings.p.registerOnSharedPreferenceChangeListener(preferenceListener);
      getSharedPreferences("phone-model-files",0).registerOnSharedPreferenceChangeListener(modelListener);
      getSharedPreferences("engine-files",0).registerOnSharedPreferenceChangeListener(modelListener);
      Notification n = captureNotification(this);
      if(Build.VERSION.SDK_INT>=29)startForeground(7, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION);else startForeground(7,n);
      captureThread = new HandlerThread("BoardLens-pixels");
      captureThread.start();
      capture = new Handler(captureThread.getLooper());
      overlay = new ArrowOverlay(this);
      floatingControls = new FloatingControls(this, settings, new FloatingControls.Actions() {
        public void scan() {
          refreshScreen();
        }
        public void stop() {

          stopSelf();
        }
        public void geometryChanged() {
          controlsMovedAt = SystemClock.elapsedRealtime();
          Handler owner = capture;
          if (owner != null) owner.post(ScreenService.this::requestTick);
        }
      });
      projection =
          getSystemService(MediaProjectionManager.class)
              .getMediaProjection(Activity.RESULT_OK, intent.getParcelableExtra("consent"));
      projection.registerCallback(
          new MediaProjection.Callback() {
            @Override
            public void onStop() {
              if(!terminating)main.post(() -> {status="Screen sharing ended · tap Start to resume";stopSelf();});
            }

            @Override
            public void onCapturedContentResize(int w, int h) {
              if (capture != null) capture.post(() -> resize(w, h));
            }
          },
          capture);
      DisplayMetrics metrics = new DisplayMetrics();
      getSystemService(WindowManager.class).getDefaultDisplay().getRealMetrics(metrics);
      images =
          ImageReader.newInstance(
              metrics.widthPixels, metrics.heightPixels, PixelFormat.RGBA_8888, 3);
      images.setOnImageAvailableListener(r->{if(reader!=null)requestTick();},capture);
      moveWorker.submit(()->{try{moves.prepare(this,settings,false);}catch(Exception ignored){}});
      evalWorker.submit(()->{try{if(settings.evaluationEnabled())evaluator.prepare(this,settings,true);}catch(Exception ignored){}});
      display =
          projection.createVirtualDisplay(
              "BoardLens phone screen",
              metrics.widthPixels,
              metrics.heightPixels,
              metrics.densityDpi,
              DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
              images.getSurface(),
              null,
              capture);
      running = true;
      if (intent.getBooleanExtra(OPEN_FLOATING_EXTRA, false)) floatingControls.open();
      syncFloatingControls();
      status = "Reading screen · open a supported chessboard";
      changed();
      capture.post(
          () -> {
            try {
              reader = new BoardReader(this);resultWatcher=new ResultWatcher();
              tick();
            } catch (Exception error) {
              problem(error);
            }
          });
    } catch (Exception error) {
      problem(error);
    }
    return START_NOT_STICKY;
  }

  private void resize(int w, int h) {
    if (display == null
        || images == null
        || w < 1
        || h < 1
        || images.getWidth() == w && images.getHeight() == h) return;
    ImageReader old = images;
    images = ImageReader.newInstance(w, h, PixelFormat.RGBA_8888, 3);
    images.setOnImageAvailableListener(r->{if(reader!=null)requestTick();},capture);
    display.resize(w, h, getResources().getDisplayMetrics().densityDpi);
    display.setSurface(images.getSurface());
    old.close();
    if(cachedFrame!=null){cachedFrame.recycle();cachedFrame=null;}
    target = null;targetGeometry=null;
    baseline = null;confirmation.clear();
    position = null;
    generation.incrementAndGet();
    moves.cancel();
    evaluator.cancel();
    publishControlsBoard(null);
    main.post(() -> {
      overlay.clear();
      if (floatingControls != null) floatingControls.displayChanged();
    });
  }

  private void refreshScreen() {
    gameEnded=false;resultRevision++;resultTarget=null;
    if(!running){stopSelf();return;}
    generation.incrementAndGet();
    moves.cancel();
    evaluator.cancel();
    lastArrows = Collections.emptyList();
    if (overlay != null) overlay.clear();
    status = "Refreshing · return to the board";
    suggestion="Waiting for a fresh board read";
    notifyStatus(status);
    changed();
    if (capture != null)
      capture.post(
          () -> {
            loseTarget();
            allowPositionReset = true;
            // Re-read the screen, but keep confirmed turn/castling history.
            // sync() validates the new placement before reusing this state.
            if(reader!=null)reader.resetTracking();
            searchedFrame=null;searchedSettings="";
            blankSince=-1;needsRead=true;cleanFrame=false;
            // Static displays may send no new image until something changes.
            // Retain the last captured pixels and force recognition again.
            lastScan = -1000;
            requestTick();
          });
  }

  private void syncFloatingControls() {
    if (floatingControls != null) floatingControls.show(running && !phoneVisible);
  }

  private boolean controlsExpanded() {
    return floatingControls != null && floatingControls.expanded();
  }

  private boolean controlsOverlap(Rect board) {
    return floatingControls != null && floatingControls.overlaps(board);
  }

  private boolean obscuredPixel(int x, int y) {
    return (floatingControls != null && floatingControls.covers(x, y)) || overlay.covers(x, y);
  }

  private void publishControlsBoard(Rect area) {
    if (Objects.equals(area, controlsBoard)) return;
    controlsBoard = area;
    main.post(() -> { if (floatingControls != null) floatingControls.setBoard(area); });
  }

  private boolean blockOccludedRead(Rect area) {
    if (!controlsOverlap(area)) return false;
    if (!controlsOccluding) {
      needsRead = true;
      confirmation.clear();
      main.post(() -> overlay.clear());
    }
    controlsOccluding = true;
    scanStage = "Move floating controls off the board";
    return true;
  }

  private void problem(Exception error) {
    status = "Stopped: " + error.getMessage();
    changed();
    main.post(() -> stopSelf());
  }

  static Notification captureNotification(Context context){
    return captureNotification(context,"Scan now to refresh · Stop to end sharing");
  }
  private static Notification captureNotification(Context context,String text){
    context.getSystemService(NotificationManager.class).createNotificationChannel(new NotificationChannel("screen","Phone screen analysis",NotificationManager.IMPORTANCE_LOW));
    int flags=PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT;
    PendingIntent stop=PendingIntent.getService(context,2,new Intent(context,ScreenService.class).setAction("STOP"),flags);
    PendingIntent scan=PendingIntent.getService(context,3,new Intent(context,ScreenService.class).setAction("REFRESH"),flags);
    PendingIntent controls=PendingIntent.getService(context,4,new Intent(context,ScreenService.class).setAction("FLOATING_CONTROLS"),flags);
    PendingIntent open=PendingIntent.getActivity(context,1,new Intent(context,PhoneScreenActivity.class),flags);
    return new Notification.Builder(context,"screen").setSmallIcon(context.getResources().getIdentifier("icon_foreground","drawable",context.getPackageName()))
      .setContentTitle("BoardLens screen analysis").setContentText(text)
      .setContentIntent(open).setOngoing(true)
      .addAction(new Notification.Action.Builder(null,"Scan now",scan).build())
      .addAction(new Notification.Action.Builder(null,"Controls",controls).build())
      .addAction(new Notification.Action.Builder(null,"Stop",stop).build()).build();
  }
  private void notifyStatus(String text){
    if(!running||notificationText.equals(text))return;notificationText=text;
    getSystemService(NotificationManager.class).notify(7,captureNotification(this,text));
  }

  private void loseTarget(){
    if(target!=null)targetLostAt=SystemClock.elapsedRealtime();
    if(target!=null||baseline!=null){generation.incrementAndGet();moves.cancel();evaluator.cancel();}
    extraEngines.cancel();
    target=null;targetGeometry=null;baseline=null;confirmation.clear();needsRead=true;
    publishControlsBoard(null);
    lastArrows=Collections.emptyList();pinned=null;displayedFen="";displayedMove="";lastAnalyzedSettings="";
    main.post(()->{if(overlay!=null)overlay.clear();});
  }

  private String settingsKey() {
    var values=new java.util.TreeMap<>(settings.p.getAll());
    values.remove("arrows");values.remove("screen_evaluation");values.remove("evaluation_position");
    values.remove(FloatingControls.ENABLED);
    values.remove(FloatingControls.BROWSER_ENABLED);
    values.remove(ArrowEngines.PREF);
    values.keySet().removeIf(ArrowEngines::isColorKey);
    values.remove("evaluation_x");values.remove("evaluation_y");values.remove("evaluation_vertical");
    return values.toString()+":"+modelRevision;
  }

  private int[] fingerprint(Bitmap b, Rect r) {
    int[] values = new int[96 * 96];
    for (int y = 0; y < 96; y++)
      for (int x = 0; x < 96; x++) {
        int xx = r.left + (int) ((x + .5f) * r.width() / 96),
            yy = r.top + (int) ((y + .5f) * r.height() / 96);
        values[y * 96 + x] = obscuredPixel(xx, yy) ? 0 : b.getPixel(xx, yy);
      }
    return values;
  }

  private boolean different(int[] a,int[] b){return ReadConfirmation.different(a,b);}
  private void checkResult(Bitmap frame){
    if(resultWatcher==null||gameEnded||position==null)return;
    Rect area=target!=null?target:resultTarget;if(area==null||SystemClock.elapsedRealtime()-lastBoardAt>6000)return;
    String root=position.fen();long revision=resultRevision;resultWatcher.offer(frame,area,reason->{Handler owner=capture;if(owner!=null)owner.post(()->{if(running&&revision==resultRevision&&position!=null&&position.fen().equals(root))visibleGameEnd(reason);});});
  }
  private void renderOverlay(){
    Rect latest=target;Rect rect=latest==null?null:new Rect(latest);BoardGeometry geometry=targetGeometry;boolean orientation=bottom;long token=generation.get();
    if(rect==null)return;
    main.post(()->{if(token!=generation.get())return;if(!running||gameEnded||phoneVisible||needsRead||baseline==null||controlsOverlap(rect)){overlay.clear();return;}if(latest!=target)return;List<String> arrows=new ArrayList<>();List<Integer> colors=new ArrayList<>();
      if(settings.arrows()){
        arrows.addAll(lastArrows);colors.addAll(lastArrowColors);
        if(colors.size()!=arrows.size())colors.clear();
        int mainColor = android.graphics.Color.parseColor(settings.mainColor());
        while(colors.size()<arrows.size())colors.add(mainColor);
        if(!colors.isEmpty())colors.set(0,mainColor);
        if(position!=null&&(!settings.onlyMine()||position.white==orientation)){
          for(var a:extraEngines.arrows(settings)){
            arrows.add(a.move());colors.add(a.color());
          }
        }
      }
      overlay.show(geometry==null?BoardGeometry.rectangle(rect.left,rect.top,rect.right,rect.bottom):geometry,orientation,arrows,colors,settings.screenEvaluation()&&settings.evaluationEnabled()&&hasEvaluationValue,evaluationBadge,whiteShare,settings.evaluationPosition());});
  }
  private void restoreArrows(){if((settings.arrows()&&(!lastArrows.isEmpty()||extraEngines.hasArrows())&&!overlay.hasArrows())||(settings.screenEvaluation()&&settings.evaluationEnabled()&&!overlay.hasEvaluation()))renderOverlay();}
  private void requestTick(){
    if(!running||reader==null||capture==null)return;
    capture.removeCallbacks(tickTask);capture.postDelayed(tickTask,Math.max(0,24-(SystemClock.elapsedRealtime()-lastTick)));
  }

  private void tick() {
    if (!running) return;
    lastTick=SystemClock.elapsedRealtime();
    Bitmap frame = null;
    String key=settingsKey();
    try {
      // Let the compositor present the uncovered board before consuming its only frame.
      if (controlsOccluding && !controlsOverlap(target)
          && SystemClock.elapsedRealtime() - controlsMovedAt < 50) return;
      ImageReader source=images;
      try (Image image = source==null?null:source.acquireLatestImage()) {
        if(phoneVisible){scanStage="Paused on BoardLens screen";return;}


        if(overlay.evaluationDragging()){scanStage="Moving evaluation bar";return;}
        if (blockOccludedRead(target)) return;
        if (controlsOccluding) {
          // A queued frame may still contain pixels from the previous overlay location.
          if (image == null) return;
          controlsOccluding = false;
        }
        if(image==null){
          if(cachedFrame==null){scanStage="Waiting for first screen frame";return;}
          if(target!=null&&baseline!=null&&!needsRead&&key.equals(lastSettings)){scanStage="Board tracked";restoreArrows();return;}
          frame=cachedFrame;
        }else{
          frames++;
          lastFrameAt=SystemClock.elapsedRealtime();captureWidth=image.getWidth();captureHeight=image.getHeight();
          Image.Plane plane=image.getPlanes()[0];
          if(target!=null&&baseline!=null&&key.equals(lastSettings)){
            int[] sampled=FrameFingerprint.read(plane.getBuffer(),image.getWidth(),image.getHeight(),plane.getRowStride(),plane.getPixelStride(),target.left,target.top,target.right,target.bottom,this::obscuredPixel);
            if(sampled!=null&&!different(baseline,sampled)){
              if(resultWatcher!=null&&resultWatcher.due()){Bitmap resultFrame=framePixels.bitmap(plane.getBuffer(),image.getWidth(),image.getHeight(),plane.getRowStride(),plane.getPixelStride());if(resultFrame!=null){checkResult(resultFrame);resultFrame.recycle();}}
              scanStage="Board tracked";needsRead=false;cleanFrame=false;confirmation.clear();restoreArrows();return;}
          }
          needsRead=true;
          frame=framePixels.bitmap(plane.getBuffer(),image.getWidth(),image.getHeight(),plane.getRowStride(),plane.getPixelStride());
          if(frame==null){scanStage="Waiting for complete screen frame";diagnostic="Waiting for a complete captured frame";return;}
          if(cachedFrame!=null)cachedFrame.recycle();cachedFrame=frame;
        }
      }
      if(CaptureVisibility.blank(frame,this::obscuredPixel)){
        if(blankSince<0){blankSince=SystemClock.elapsedRealtime();loseTarget();}
        if(SystemClock.elapsedRealtime()-blankSince>=400){
          scanStage="Screen pixels blank or protected";diagnostic="Blank captured content";
          String message="Screen is blank or capture is blocked · open a visible board";
          if(!message.equals(status)){status=message;suggestion="No board pixels available";notifyStatus("Screen is blank or capture is blocked");changed();}
        }
        return;
      }
      blankSince=-1;checkResult(frame);
      if (!key.equals(lastSettings)) {
        lastSettings = key;
        if (!settings.turn().equals(lastTurn) && !settings.turn().equals("Auto")) position = null;
        lastTurn = settings.turn();lastOrientation=settings.orientation();
        generation.incrementAndGet();
        moves.cancel();
        evaluator.cancel();
        baseline = null;
        confirmation.clear();
      }
      if (target != null && !new Rect(0, 0, frame.getWidth(), frame.getHeight()).contains(target)) {
        loseTarget();
      }
      if (target != null && baseline != null && !different(baseline, fingerprint(frame, target))) {
        scanStage="Board tracked";
        needsRead=false;cleanFrame=false;confirmation.clear();restoreArrows();
        return;
      }
      // Remove our own pixels only after a real board change; never blink unchanged arrows.
      if (!cleanFrame && target != null && overlay.hasContent()) {
        cleanFrame = true;
        main.post(() -> overlay.clear());
        return;
      }
      cleanFrame = false;
      if (target == null && SystemClock.elapsedRealtime() - lastScan < 120) return;
      // Recognition is deterministic: do not keep running every model on the
      // same rejected screenshot while waiting for a new capture.
      if(frame==searchedFrame&&key.equals(searchedSettings))return;
      lastScan = SystemClock.elapsedRealtime();
      BoardReader.Read read=target==null?null:confirmation.poll(fingerprint(frame,target),SystemClock.elapsedRealtime());
      // A new capture can arrive before the stability interval has elapsed.
      // Keep the candidate's original timestamp; re-reading here used to reset
      // it repeatedly, so a still board could wait forever for a move.
      if(read==null&&confirmation.pending())return;
      boolean confirmed=read!=null;
      boolean discovering=target==null;
      scanStage=target==null?"Searching screen for board":"Reading board pieces";
      if(read==null){reads++;read=target==null?reader.read(frame,null,settings.orientation()):reader.track(frame,target,settings.orientation());}
      diagnostic = reader.diagnostic;
      if (read == null) {
        if(discovering){searchedFrame=frame;searchedSettings=key;if(!gameEnded){status="Looking for a complete supported board";notifyStatus("Looking for a complete board · scanning automatically");changed();}}
        confirmation.clear();
        if (++failures >= 3) {
          loseTarget();
          if(!gameEnded){status = "Looking for a complete supported board";
          notifyStatus("Looking for a complete board · scanning automatically");changed();}
        }
        return;
      }
      publishControlsBoard(read.rect());
      if (blockOccludedRead(read.rect())) return;
      failures = 0;
      if(!confirmed)read=resolveOrientation(read,position==null?new ChessPosition(ChessPosition.START_FEN):position,settings.orientation());
      target = read.rect();
      targetGeometry=read.geometry();
      // Highlights and selection effects can animate while every piece stays
      // still. Two independent matching recognitions confirm that position.
      if(!confirmed)confirmed=confirmation.agrees(read,SystemClock.elapsedRealtime(),ScreenService::sameRead);
      if(!confirmed){scanStage="Confirming board position";confirmation.set(read,fingerprint(frame,target),SystemClock.elapsedRealtime());return;}
      confirmation.clear();
      String turn = settings.turn();
      boolean canReset = allowPositionReset || targetLostAt>=0 && SystemClock.elapsedRealtime()-targetLostAt>1000;
      ChessPosition synced = position==null ? null : ChessPosition.sync(position,read.placement(),turn,false);
      boolean known=synced!=null && synced.sharesHistory(position) && (turnKnown || !synced.placement().equals(position.placement()));
      if(synced==null && position!=null && !turnKnown && turn.equals("Auto")){
        ChessPosition alternate=new ChessPosition(position.placement()+" "+(position.white?"b":"w")+" - - 0 1");
        if(alternate.valid()){
          synced=ChessPosition.sync(alternate,read.placement(),turn,false);
          known=synced!=null;
        }
      }
      if(synced==null) {
        Boolean hint=LastMoveHint.read(frame,read.rect(),read.placement(),read.whiteBottom());
        if(turn.equals("Auto") && (position==null || canReset)){
          synced=ChessPosition.sync(new ChessPosition(ChessPosition.START_FEN),read.placement(),turn,false);
          known=synced!=null && (hint==null || synced.white==hint);
          if(!known)synced=null;
        }
        if(synced==null && (position==null || canReset || hint!=null && turn.equals("Auto"))) {
          synced=ChessPosition.sync(null,read.placement(),turn.equals("Auto")&&hint!=null?(hint?"White":"Black"):turn,true);


        }
      }
      if (synced == null) {
        scanStage="Waiting for legal position";
        searchedFrame=frame;searchedSettings=key;
        status = "Waiting for a complete move · Scan now for a different board";
        changed();
        return;
      }
      boolean orientationChanged=bottom!=read.whiteBottom();
      bottom=read.whiteBottom();
      boolean changedPosition = position == null || !position.fen().equals(synced.fen());
      turnKnown=!turn.equals("Auto")||known||synced.placement().equals(ChessPosition.START_PLACEMENT)||synced.inCheck(synced.white);
      position = synced;allowPositionReset=false;targetLostAt=-1;

      if(position.placement().equals("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR")&&(!gameEnded||changedPosition)){gameEnded=false;gameEndReason="";}
      resultTarget=new Rect(target);lastBoardAt=SystemClock.elapsedRealtime();scanStage="Board tracked";
      notifyStatus("Board detected · scanning automatically");
      fen = position.fen();
      trackedWhiteBottom = bottom;
      trackedPosition = position;
      if (changedPosition || orientationChanged || lastScannedBoard == null)
        lastScannedBoard = new PracticeSnapshot(position, bottom);
      baseline = fingerprint(frame, target);needsRead=false;
      if(changedPosition||orientationChanged||preview==null){
        Bitmap crop=Bitmap.createBitmap(frame,target.left,target.top,target.width(),target.height());
        preview=Bitmap.createScaledBitmap(crop,320,Math.max(1,Math.round(320f*crop.getHeight()/crop.getWidth())),true);
        if(preview==frame)preview=frame.copy(Bitmap.Config.ARGB_8888,false);
        if(crop!=frame&&crop!=preview)crop.recycle();
      }
      status =
          (bottom ? "White" : "Black")
              + " at bottom · "
              + (position.white ? "White" : "Black")
              + " to move"
              + (settings.turn().equals("Auto") ? " · turn inferred" : "");
      changed();
      if(gameEnded){status="Game over · "+gameEndReason;lastArrows=Collections.emptyList();main.post(()->overlay.clear());changed();return;}
      if (changedPosition || orientationChanged || !key.equals(lastAnalyzedSettings)) {
        lastAnalyzedSettings = key;
        pinned=null;displayedFen="";displayedMove="";
        lastArrows = Collections.emptyList();
        analyze(position, new Rect(target), bottom);
      } else restoreArrows();

    } catch (Exception error) {
      scanStage="Retrying screen read";
      status = "Read paused: " + error.getMessage();
      changed();
    } finally {
      if (frame != null&&frame!=cachedFrame) frame.recycle();
      if (running && capture != null){capture.removeCallbacks(tickTask);capture.postDelayed(tickTask, 32);}
    }
  }

  private String lastAnalyzedSettings = "";

  static BoardReader.Read resolveOrientation(BoardReader.Read read,ChessPosition previous,String mode){
    if(previous==null||!mode.equals("Auto"))return read;
    String reversed=ChessPosition.rotatePlacement(read.placement());
    boolean current=ChessPosition.sync(previous,read.placement(),"Auto",false)!=null;
    if(current)return read;
    boolean opposite=ChessPosition.sync(previous,reversed,"Auto",false)!=null;
    return opposite?new BoardReader.Read(read.rect(),reversed,!read.whiteBottom(),read.confidence(),read.geometry()):read;
  }

  static boolean sameRead(BoardReader.Read a,BoardReader.Read b){
    if(!a.placement().equals(b.placement())||a.whiteBottom()!=b.whiteBottom())return false;
    double[] x=a.geometry().corners,y=b.geometry().corners;double tolerance=Math.max(2,a.rect().width()*.005);
    for(int i=0;i<8;i++)if(Math.abs(x[i]-y[i])>tolerance)return false;return true;
  }

  private void analyze(ChessPosition board, Rect rect, boolean whiteBottom) {


    long token = generation.incrementAndGet();
    PhoneSettings jobSettings=settings.snapshot();
    moves.cancel();
    evaluator.cancel();
    suggestion = EngineCatalog.get(settings.engine()).maia()?"Starting "+EngineCatalog.get(settings.engine()).name()+"…":"Thinking…";
    evaluation = "Updating "+EngineCatalog.get(settings.evaluator()).name()+" evaluation…";
    renderOverlay();
    changed();
    if (board.legal().isEmpty()) {
      extraEngines.cancel();

      boolean check=board.inCheck(board.white);suggestion=check?"Checkmate":"Draw · no legal moves";
      evaluation=check?(board.white?"Black wins by checkmate":"White wins by checkmate"):"Stalemate";
      hasEvaluationValue=true;whiteShare=check?(board.white?0:1):.5f;evaluationBadge=check?"Mate":"Draw";lastArrows=Collections.emptyList();
      status="Game over · "+suggestion;notifyStatus(status);renderOverlay();changed();return;
    }
    if(capture!=null)extraEngines.request(this,board,jobSettings,capture,this::renderOverlay);
    if (!EngineCatalog.ready(this,settings.engine())) {
      suggestion="Download "+EngineCatalog.get(settings.engine()).name()+" in Models";changed();
    }else moveWorker.submit(
        () -> {
          try {
            if(token!=generation.get()||!running)return;
            PhoneEngine.Result result = moves.recommend(this,board,jobSettings,()->token==generation.get()&&running,
                (r,rootComplete) -> { if(rootComplete||settings.early())publishMoves(r,board,rect,whiteBottom,token,rootComplete); });
            publishMoves(result, board, rect, whiteBottom, token, true);
          } catch (CancellationException ignored) {
          } catch (Exception error) {
            if (token == generation.get()) {
              suggestion = "Engine: " + error.getMessage();
              changed();
            }
          }
        });
    if(!settings.evaluationEnabled()){evaluation="Evaluation off";evaluationBadge="Off";evalWorker.submit(evaluator::close);renderOverlay();changed();return;}
    evalWorker.submit(
        () -> {
          try {
            if(token!=generation.get()||!running)return;
            if(!EngineCatalog.ready(this,settings.evaluator())){evaluation="Download "+EngineCatalog.get(settings.evaluator()).name()+" for evaluation";evaluationBadge="Data";renderOverlay();changed();return;}
            LocalEngines.Evaluated result=evaluator.evaluate(this,board,jobSettings,r->publishEvaluation(r,board,token));
            publishEvaluation(result,board,token);
          } catch (CancellationException ignored) {
          } catch (Exception error) {
            if (token == generation.get()) {
              evaluation = "Evaluation: " + error.getMessage();evaluationBadge="!";renderOverlay();
              changed();
            }
          }
        });
  }

  private void publishEvaluation(LocalEngines.Evaluated result,ChessPosition board,long token){
    Handler owner=capture;
    if(owner!=null&&Looper.myLooper()!=owner.getLooper()){owner.post(()->publishEvaluation(result,board,token));return;}
    if(token!=generation.get()||!running||!settings.evaluationEnabled()||position==null||!position.fen().equals(board.fen()))return;
    hasEvaluationValue=true;evaluation=result.text();whiteShare=result.whiteShare();evaluationBadge=result.badge();changed();renderOverlay();
  }

  private String displayedFen = "", displayedMove = "";
  private PhoneEngine.Result pinned;

  private void publishMoves(
      PhoneEngine.Result result,
      ChessPosition board,
      Rect rect,
      boolean whiteBottom,
      long token,
      boolean finished) {
    Handler owner=capture;
    if(owner!=null&&Looper.myLooper()!=owner.getLooper()){
      owner.post(()->publishMoves(result,board,rect,whiteBottom,token,finished));return;
    }
    applyMoves(result,board,rect,whiteBottom,token,finished);
  }

  private void applyMoves(PhoneEngine.Result result,ChessPosition board,Rect rect,
      boolean whiteBottom,long token,boolean finished){
    if (token != generation.get() || result.lines().isEmpty() || !running
        || gameEnded || position==null || !board.fen().equals(position.fen()) || !result.fen().equals(board.fen())) return;
    if(settings.lockMove()){
      if(pinned!=null&&pinned.fen().equals(result.fen()))result=pinned;
      else pinned=result;
    }else pinned=null;

    final BoardGeometry arrowGeometry=targetGeometry==null?BoardGeometry.rectangle(rect.left,rect.top,rect.right,rect.bottom):targetGeometry;
    PhoneEngine.Line first = result.lines().get(0);
    if (settings.steady()
        && !finished
        && !lastArrows.isEmpty()
        && displayedFen.equals(result.fen())
        && result.lines().size() <= lastArrows.size()
        && !displayedMove.equals(first.move())) return;
    displayedFen = result.fen();
    displayedMove = first.move();
    StringBuilder text = new StringBuilder();
    List<String> arrows = new ArrayList<>();
    List<Integer> arrowColors = new ArrayList<>();
    int rank = 0;
    for (PhoneEngine.Line line : result.lines()) {
      if (settings.onlyMine() && board.white != whiteBottom) {
        // Future replies are conditional; never draw them as a current move.
        if(rank==0&&settings.predict()&&line.pv().size()>1){
          ChessPosition next=board.play(line.move());String reply=line.pv().get(1);
          if(next.legal().contains(reply)){text.append("Waiting for opponent. If ").append(board.simple(line.move())).append(":\n").append(next.simple(reply)).append(" · predicted only");rank++;}
        }
        continue;
      }
      if(!board.legal().contains(line.move()))continue;
      text.append(++rank).append(". ").append(board.simple(line.move())).append('\n');
      arrows.add(line.move());arrowColors.add(android.graphics.Color.parseColor(settings.arrowColor(rank - 1)));
      if (rank == 1 && settings.predict() && settings.predictionPlies()>1 && line.pv().size() > 1) {
        ChessPosition next = board.play(line.move());
        String reply = line.pv().get(1);
        if (next.legal().contains(reply)) {
          text.append("Reply: ").append(next.simple(reply)).append('\n');
          if (!settings.onlyMine()){arrows.add(reply);arrowColors.add(0xff51d9da);}
          next = next.play(reply);
          if (settings.predictionPlies()>2 && line.pv().size() > 2 && next.legal().contains(line.pv().get(2)))
            text.append("Then: ").append(next.simple(line.pv().get(2))).append('\n');
        }
      }
    }
    if(token!=generation.get()||!running)return;
    lastArrows = new ArrayList<>(arrows);lastArrowColors=List.copyOf(arrowColors);
    suggestion = text.length() == 0 ? "Waiting for your turn" : text.toString().trim()+(finished?"":"\nThinking…");
    changed();
    if(token==generation.get())renderOverlay();
  }

  @Override
  public void onDestroy() {
    terminating=true;

    if(settings!=null)settings.p.unregisterOnSharedPreferenceChangeListener(preferenceListener);
    getSharedPreferences("phone-model-files",0).unregisterOnSharedPreferenceChangeListener(modelListener);
    getSharedPreferences("engine-files",0).unregisterOnSharedPreferenceChangeListener(modelListener);
    active = null;
    running = false;
    scanStage="Stopped";
    trackedPosition=null;
    generation.incrementAndGet();
    moves.cancel();
    evaluator.cancel();
    extraEngines.close();
    moveWorker.close(moves::close);
    evalWorker.close(evaluator::close);
    main.removeCallbacksAndMessages(null);
    if (floatingControls != null) floatingControls.show(false);
    if (overlay != null) overlay.remove();
    if (capture != null) {
      capture.removeCallbacksAndMessages(null);
      capture.post(
          () -> {
            if (display != null) display.release();
            if (images != null) images.close();
            if(cachedFrame!=null){cachedFrame.recycle();cachedFrame=null;}
            if (projection != null) projection.stop();
            if(resultWatcher!=null)resultWatcher.close();
            if (reader != null)
              try {
                reader.close();
              } catch (Exception ignored) {
              }
            if (captureThread != null) captureThread.quitSafely();
          });
    }
    if (!status.startsWith("Stopped:")&&!status.startsWith("Screen sharing ended")) status = "Stopped";
    changed();
    stopForeground(STOP_FOREGROUND_REMOVE);
    super.onDestroy();
  }
}
