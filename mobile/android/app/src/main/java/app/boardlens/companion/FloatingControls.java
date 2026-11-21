package app.boardlens.companion;

import android.content.Context;
import android.content.SharedPreferences;
import android.content.res.ColorStateList;
import android.graphics.Canvas;
import android.graphics.Insets;
import android.graphics.Paint;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.os.Build;
import android.provider.Settings;
import android.text.TextUtils;
import android.util.DisplayMetrics;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.view.WindowInsets;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import static app.boardlens.companion.FloatingControlLayout.Box;

/** A bounded overlay window. All views and window operations run on the main thread. */
final class FloatingControls {
  static final String ENABLED = "floating_controls";
  static final String BROWSER_ENABLED = "browser_floating_controls";
  private static final int PANEL = 0xff151322;
  private static final int SURFACE = 0xff201c31;
  private static final int BORDER = 0xff3d3552;
  private static final int SELECTED = 0xff382854;
  private static final int ACCENT = 0xffdac8ff;
  private static final int MUTED = 0xffb5aec8;
  private static final int ALERT = 0xfff9b5c3;
  private static final int BUBBLE_DP = 52;
  private enum Glyph { MINIMIZE, CLOSE, RESIZE }
  interface Actions {
    void scan();
    void stop();
    void geometryChanged();
  }

  private final Context context;
  private final WindowManager windows;
  private final FrameLayout host;
  private final String visibilityKey;
  private final PhoneSettings settings;
  private final SharedPreferences layout;
  private final MobileUi ui;
  private final Actions actions;
  private final LinearLayout root;
  private final WindowManager.LayoutParams params;
  private final int slop;
  private ScrollView scroll;
  private final Button[] tabs = new Button[3];
  private int selectedTab;
  private TextView obstruction;
  private Box safe, geometry, board;
  private volatile Box visibleBounds;
  private volatile boolean expanded;
  private boolean attached, permittedToShow;
  private int widthDp, heightDp;
  private float anchorX, anchorY;

  FloatingControls(Context context, PhoneSettings settings, Actions actions) {
    this(context, settings, actions, null);
  }

  FloatingControls(Context context, PhoneSettings settings, Actions actions, FrameLayout host) {
    this.context = context;
    this.settings = settings;
    this.actions = actions;
    this.host = host;
    visibilityKey = host == null ? ENABLED : BROWSER_ENABLED;
    windows = context.getSystemService(WindowManager.class);
    layout = context.getSharedPreferences(host == null ? "floating-controls-layout"
        : "browser-floating-controls-layout", Context.MODE_PRIVATE);
    ui = new MobileUi(context);
    slop = ViewConfiguration.get(context).getScaledTouchSlop();
    widthDp = layout.getInt("width", 274);
    heightDp = layout.getInt("height", 296);
    anchorX = layout.getFloat("x", 1f);
    anchorY = layout.getFloat("y", host == null ? 0f : 1f);
    root = ui.column();
    params = new WindowManager.LayoutParams(1, 1,
        WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
            | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL
            | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
        PixelFormat.TRANSLUCENT);
    params.gravity = Gravity.TOP | Gravity.LEFT;
    params.setTitle("BoardLens floating settings");
    if (Build.VERSION.SDK_INT >= 30) {
      params.setFitInsetsTypes(0);
      params.layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS;
    } else if (Build.VERSION.SDK_INT >= 28) {
      params.layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
    }
  }

  boolean expanded() { return expanded && visibleBounds != null; }
  boolean covers(int x, int y) {
    Box bounds = visibleBounds;
    return bounds != null && bounds.left() <= x && x < bounds.right()
        && bounds.top() <= y && y < bounds.bottom();
  }
  boolean overlaps(Rect rect) {
    Box bounds = visibleBounds;
    return bounds != null && rect != null && bounds.left() < rect.right && bounds.right() > rect.left
        && bounds.top() < rect.bottom && bounds.bottom() > rect.top;
  }

  void show(boolean visible) {
    permittedToShow = visible;
    boolean enabled = settings.p.getBoolean(visibilityKey, true);
    if (!enabled) expanded = false;
    if (!visible || !enabled || !canShow()) {
      detach();
      return;
    }
    if (!attached) display(expanded);
  }

  void toggle() {
    if (expanded && settings.p.getBoolean(visibilityKey, true)) collapse();
    else open();
  }

  void open() {
    if (host == null && !Settings.canDrawOverlays(context)) return;
    expanded = true;
    settings.p.edit().putBoolean(visibilityKey, true).apply();
    if (permittedToShow && canShow()) display(true);
  }

  void close() {
    expanded = false;
    settings.p.edit().putBoolean(visibilityKey, false).apply();
    detach();
  }

  void displayChanged() {
    if (attached) display(expanded);
    else if (permittedToShow) show(true);
  }

  void setBoard(Rect rect) {
    board = rect == null ? null : new Box(rect.left, rect.top, rect.right, rect.bottom);
    if (attached && !expanded && board != null && geometry.overlaps(board)) {
      place(FloatingControlLayout.dock(safe, geometry, board, ui.dp(8)));
    }
    updateObstruction();
  }

  void collapse() {
    expanded = false;
    if (attached) display(false);
  }

  private void detach() {
    if (attached) {
      if (host != null) host.removeView(root);
      else {
        try { windows.removeView(root); }
        catch (IllegalArgumentException ignored) { }
      }
      attached = false;
    }
    publish(null);
  }

  private void display(boolean open) {
    expanded = open;
    safe = availableSpace();
    int width = ui.dp(open ? widthDp : BUBBLE_DP);
    int height = ui.dp(open ? heightDp : BUBBLE_DP);
    Box desired = FloatingControlLayout.fit(safe,
        safe.left() + Math.round(anchorX * Math.max(0, safe.width() - width)),
        safe.top() + Math.round(anchorY * Math.max(0, safe.height() - height)), width, height);
    root.removeAllViews();
    root.setBackground(open ? shape(PANEL, 16, BORDER) : null);
    if (open) buildPanel();
    else {
      obstruction = null;
      ImageButton bubble = new ImageButton(context);
      bubble.setScaleType(ImageView.ScaleType.FIT_CENTER);
      bubble.setPadding(ui.dp(5), ui.dp(5), ui.dp(5), ui.dp(5));
      bubble.setImageResource(logoResource());
      bubble.setBackground(ripple(PANEL, 26, BORDER));
      bubble.setContentDescription("Open BoardLens floating menu. Drag to move.");
      bubble.setOnClickListener(view -> display(true));
      root.addView(bubble, new LinearLayout.LayoutParams(-1, -1));
      gesture(bubble, false);
    }
    place(open ? FloatingControlLayout.dockPanel(safe, desired, board, ui.dp(8), ui.dp(230))
        : FloatingControlLayout.dock(safe, desired, board, ui.dp(8)));
  }

  private void place(Box box) {
    geometry = box;
    if (host != null) {
      FrameLayout.LayoutParams inApp = new FrameLayout.LayoutParams(box.width(), box.height(),
          Gravity.TOP | Gravity.LEFT);
      inApp.leftMargin = box.left();
      inApp.topMargin = box.top();
      if (attached) root.setLayoutParams(inApp);
      else { host.addView(root, inApp); attached = true; }
      publish(box);
      updateObstruction();
      return;
    }
    params.x = box.left();
    params.y = box.top();
    params.width = box.width();
    params.height = box.height();
    try {
      if (attached) windows.updateViewLayout(root, params);
      else { windows.addView(root, params); attached = true; }
      publish(box);
    } catch (SecurityException | WindowManager.BadTokenException | IllegalArgumentException denied) {
      detach();
    }
    updateObstruction();
  }

  private void publish(Box next) {
    if (java.util.Objects.equals(visibleBounds, next)) return;
    visibleBounds = next;
    actions.geometryChanged();
  }

  private Box availableSpace() {
    int gap = ui.dp(8);
    if (host != null)
      return new Box(gap, gap, host.getWidth() - gap, host.getHeight() - gap);
    if (Build.VERSION.SDK_INT >= 30) {
      var metrics = windows.getCurrentWindowMetrics();
      Rect bounds = metrics.getBounds();
      Insets insets = metrics.getWindowInsets().getInsetsIgnoringVisibility(
          WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
      return new Box(bounds.left + insets.left + gap, bounds.top + insets.top + gap,
          bounds.right - insets.right - gap, bounds.bottom - insets.bottom - gap);
    }
    DisplayMetrics metrics = new DisplayMetrics();
    windows.getDefaultDisplay().getRealMetrics(metrics);
    return new Box(gap, ui.dp(40), metrics.widthPixels - gap, metrics.heightPixels - ui.dp(48));
  }

  private boolean canShow() {
    return host == null ? Settings.canDrawOverlays(context)
        : host.getWidth() > ui.dp(16) && host.getHeight() > ui.dp(16);
  }

  private void buildPanel() {
    LinearLayout header = row();
    header.setPadding(ui.dp(10), ui.dp(3), ui.dp(3), ui.dp(2));
    LinearLayout handle = row();
    ImageView logo = new ImageView(context);
    logo.setImageResource(logoResource());
    logo.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
    LinearLayout.LayoutParams mark = new LinearLayout.LayoutParams(ui.dp(28), ui.dp(28));
    mark.rightMargin = ui.dp(8);
    handle.addView(logo, mark);
    TextView title = ui.text("BoardLens", 16, MobileUi.FG, true);
    title.setSingleLine();
    title.setEllipsize(TextUtils.TruncateAt.END);
    handle.addView(title, new LinearLayout.LayoutParams(0, -2, 1));
    handle.setContentDescription("BoardLens floating menu. Drag to move.");
    header.addView(handle, new LinearLayout.LayoutParams(0, ui.dp(44), 1));
    gesture(handle, false);
    ImageButton minimize = iconButton(Glyph.MINIMIZE, "Minimize floating menu", this::collapse);
    header.addView(minimize, new LinearLayout.LayoutParams(ui.dp(44), ui.dp(44)));
    ImageButton close = iconButton(Glyph.CLOSE, "Close floating menu", this::close);
    header.addView(close, new LinearLayout.LayoutParams(ui.dp(44), ui.dp(44)));
    root.addView(header);
    addTabs();

    obstruction = ui.text("Move the menu off the board to resume scanning.", 12, ALERT, false);
    obstruction.setPadding(ui.dp(12), ui.dp(5), ui.dp(12), ui.dp(5));
    obstruction.setVisibility(View.GONE);
    root.addView(obstruction);

    scroll = new ScrollView(context);
    scroll.setClipToPadding(false);
    root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
    selectTab(selectedTab);

    View rule = new View(context);
    rule.setBackgroundColor(BORDER);
    root.addView(rule, new LinearLayout.LayoutParams(-1, ui.dp(1)));
    LinearLayout footer = row();
    footer.setPadding(ui.dp(5), 0, ui.dp(4), ui.dp(2));
    footer.addView(textButton("Scan now", ACCENT, () -> { collapse(); actions.scan(); }),
        new LinearLayout.LayoutParams(0, ui.dp(44), 1));
    footer.addView(textButton("Stop", ALERT, actions::stop),
        new LinearLayout.LayoutParams(0, ui.dp(44), 1));
    ImageButton resize = iconButton(Glyph.RESIZE, "Resize floating menu", this::presetSize);
    footer.addView(resize, new LinearLayout.LayoutParams(ui.dp(44), ui.dp(44)));
    gesture(resize, true);
    root.addView(footer);
  }

  private void addTabs() {
    LinearLayout strip = row();
    strip.setPadding(ui.dp(4), ui.dp(3), ui.dp(4), ui.dp(3));
    strip.setBackground(shape(SURFACE, 10, 0));
    String[] labels = {"Quick", "Engine", "Board"};
    for (int i = 0; i < labels.length; i++) {
      int tab = i;
      tabs[i] = textButton(labels[i], MUTED, () -> selectTab(tab));
      strip.addView(tabs[i], new LinearLayout.LayoutParams(0, ui.dp(40), 1));
    }
    LinearLayout.LayoutParams layout = new LinearLayout.LayoutParams(-1, -2);
    layout.setMargins(ui.dp(10), 0, ui.dp(10), ui.dp(4));
    root.addView(strip, layout);
  }

  private void selectTab(int tab) {
    selectedTab = tab;
    for (int i = 0; i < tabs.length; i++) {
      boolean selected = i == tab;
      tabs[i].setSelected(selected);
      tabs[i].setTextColor(selected ? ACCENT : MUTED);
      tabs[i].setBackground(ripple(selected ? SELECTED : SURFACE, 8, 0));
    }
    switch (tab) {
      case 1 -> showEngines();
      case 2 -> showBoardOptions();
      default -> showQuick();
    }
  }

  private int logoResource() {
    return context.getResources().getIdentifier("boardlens_square", "drawable", context.getPackageName());
  }

  private GradientDrawable shape(int fill, int radius, int stroke) {
    GradientDrawable shape = new GradientDrawable();
    shape.setColor(fill);
    shape.setCornerRadius(ui.dp(radius));
    if (stroke != 0) shape.setStroke(ui.dp(1), stroke);
    return shape;
  }

  private RippleDrawable ripple(int color, int radius, int stroke) {
    return new RippleDrawable(ColorStateList.valueOf(0x35dac8ff),
        shape(color, radius, stroke), null);
  }

  private Button textButton(String text, int color, Runnable action) {
    Button button = ui.button(text, false, action);
    button.setTextSize(13);
    button.setTextColor(color);
    button.setMinHeight(0);
    button.setMinimumHeight(0);
    button.setMinWidth(0);
    button.setMinimumWidth(0);
    button.setPadding(ui.dp(8), 0, ui.dp(8), 0);
    button.setSingleLine();
    button.setEllipsize(TextUtils.TruncateAt.END);
    button.setBackground(ripple(PANEL, 8, 0));
    return button;
  }

  private ImageButton iconButton(Glyph icon, String description, Runnable action) {
    ImageButton button = new ImageButton(context);
    button.setScaleType(ImageView.ScaleType.CENTER);
    button.setPadding(0, 0, 0, 0);
    button.setBackground(ripple(PANEL, 8, 0));
    button.setContentDescription(description);
    button.setOnClickListener(view -> action.run());
    button.setImageDrawable(new Drawable() {
      private final Paint pen = new Paint(Paint.ANTI_ALIAS_FLAG);

      @Override public void draw(Canvas canvas) {
        int saved = canvas.save();
        Rect bounds = getBounds();
        canvas.translate(bounds.left, bounds.top);
        canvas.scale(bounds.width() / 20f, bounds.height() / 20f);
        pen.setColor(icon == Glyph.CLOSE ? ALERT : ACCENT);
        pen.setStrokeWidth(1.55f);
        pen.setStrokeCap(Paint.Cap.ROUND);
        switch (icon) {
          case MINIMIZE -> canvas.drawLine(5, 11, 15, 11, pen);
          case CLOSE -> {
            canvas.drawLine(6, 6, 14, 14, pen);
            canvas.drawLine(14, 6, 6, 14, pen);
          }
          case RESIZE -> {
            canvas.drawLine(5, 14, 14, 5, pen);
            canvas.drawLine(9, 15, 15, 9, pen);
            canvas.drawLine(13, 15, 15, 13, pen);
          }
        }
        canvas.restoreToCount(saved);
      }

      @Override public int getIntrinsicWidth() { return ui.dp(20); }
      @Override public int getIntrinsicHeight() { return ui.dp(20); }
      @Override public void setAlpha(int alpha) {}
      @Override public void setColorFilter(android.graphics.ColorFilter filter) {}
      @Override public int getOpacity() { return PixelFormat.TRANSLUCENT; }
    });
    return button;
  }

  private void updateObstruction() {
    if (obstruction != null)
      obstruction.setVisibility(board != null && geometry.overlaps(board) ? View.VISIBLE : View.GONE);
  }

  private void gesture(View handle, boolean resizing) {
    handle.setOnTouchListener(new View.OnTouchListener() {
      private int pointer;
      private float downX, downY;
      private Box start;
      private boolean moved;

      @Override public boolean onTouch(View view, MotionEvent event) {
        switch (event.getActionMasked()) {
          case MotionEvent.ACTION_DOWN -> {
            pointer = event.getPointerId(0);
            downX = event.getRawX();
            downY = event.getRawY();
            start = geometry;
            moved = false;
            return true;
          }
          case MotionEvent.ACTION_MOVE -> {
            if (event.getPointerId(0) != pointer) return true;
            int dx = Math.round(event.getRawX() - downX), dy = Math.round(event.getRawY() - downY);
            if (moved || Math.abs(dx) > slop || Math.abs(dy) > slop) {
              moved = true;
              place(resizing
                  ? FloatingControlLayout.resize(safe, start, dx, dy, ui.dp(230), ui.dp(230))
                  : FloatingControlLayout.fit(safe, start.left() + dx, start.top() + dy,
                      start.width(), start.height()));
            }
            return true;
          }
          case MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
            if (moved) remember(resizing);
            else if (event.getActionMasked() == MotionEvent.ACTION_UP) view.performClick();
            return true;
          }
          default -> { return true; }
        }
      }
    });
  }

  private void presetSize() {
    int width = ui.dp(heightDp > 340 ? 250 : 310), height = ui.dp(heightDp > 340 ? 300 : 430);
    place(FloatingControlLayout.fit(safe, geometry.left(), geometry.top(), width, height));
    remember(true);
  }

  private void remember(boolean resizing) {
    anchorX = (geometry.left() - safe.left()) / (float) Math.max(1, safe.width() - geometry.width());
    anchorY = (geometry.top() - safe.top()) / (float) Math.max(1, safe.height() - geometry.height());
    var edit = layout.edit().putFloat("x", anchorX).putFloat("y", anchorY);
    if (resizing) {
      float density = context.getResources().getDisplayMetrics().density;
      widthDp = Math.round(geometry.width() / density);
      heightDp = Math.round(geometry.height() / density);
      edit.putInt("width", widthDp).putInt("height", heightDp);
    }
    edit.apply();
  }

  private LinearLayout row() {
    LinearLayout row = new LinearLayout(context);
    row.setGravity(Gravity.CENTER_VERTICAL);
    return row;
  }

  private LinearLayout page(Runnable back) {
    LinearLayout page = ui.column();
    page.setPadding(ui.dp(10), 0, ui.dp(10), ui.dp(5));
    scroll.removeAllViews();
    scroll.addView(page);
    scroll.scrollTo(0, 0);
    if (back != null) button(page, "‹ Back", back);
    return page;
  }

  private void button(LinearLayout page, String label, Runnable action) {
    Button button = textButton(label, MobileUi.FG, action);
    button.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
    button.setBackground(ripple(SURFACE, 8, 0));
    LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, ui.dp(44));
    params.bottomMargin = ui.dp(3);
    page.addView(button, params);
  }

  private void showArrowEngines(Runnable back) {
    new ArrowEngineMenu(ui, settings, back, body -> {
      scroll.removeAllViews();
      scroll.addView(body);
      scroll.scrollTo(0, 0);
    }).overview();
  }

  private void showQuick() {
    LinearLayout page = page(null);
    button(page, "Arrow engines", () -> showArrowEngines(this::showQuick));
    toggle(page, host == null ? "Screen arrows" : "Browser arrows", "arrows", true);
    toggle(page, "Evaluation bar", "screen_evaluation", true);
    toggle(page, "Only my color", "onlyMine", false);
  }

  private void showEngines() {
    LinearLayout page = page(null);
    button(page, "Arrow engines", () -> showArrowEngines(this::showEngines));
    engine(page, "Move engine", false);
    EngineCatalog.Entry move = EngineCatalog.get(settings.engine());
    if (!move.policy() && !move.tiny()) {
      picker(page, "Search limit", "mode", settings.mode(), ArrowEngines.MODES, this::showEngines);
      if (!settings.mode().equals("Time"))
        number(page, "Depth", "depth", settings.depth(), 1, 60, 1);
    }
    if (move.policy() || move.tiny() || !settings.mode().equals("Depth"))
      time(page, "Move time", "seconds", settings.seconds(), .05f);
    if (move.policy() || move.id().equals("flounder")) number(page, "Target Elo", "rating", settings.rating(), 600, 2600, 50);
    if (move.id().equals("stockfish")) number(page, "Stockfish skill", "skill", settings.skill(), 0, 20, 1);
    if (move.kind().equals("stockfish"))
      picker(page, "Playing style", "style", settings.style(),
          List.of("Balanced", "Aggressive", "Defensive", "Human-like"), this::showEngines);
    if (!move.tiny())
      number(page, "CPU threads", "threads", settings.threads(), 1,
          Math.max(1, Math.min(8, Runtime.getRuntime().availableProcessors())), 1);
    if (!move.tiny()) number(page, "Suggested moves", "moves", settings.moves(), 1, 5, 1);
    toggle(page, "Evaluate position", "evaluation_enabled", true, this::showEngines);
    if (settings.evaluationEnabled()) {
      engine(page, "Evaluation engine", true);
      if (!EngineCatalog.get(settings.evaluator()).policy()) {
        time(page, "Evaluation time", "evaluation_seconds", settings.evaluationSeconds(), .03f);
        number(page, "Evaluation depth", "evaluation_depth", settings.evaluationDepth(), 1, 40, 1);
      }
    }
  }

  private void showBoardOptions() {
    LinearLayout page = page(null);
    if (host == null) {
      picker(page, "Orientation", "orientation", settings.orientation(),
          List.of("Auto", "White at bottom", "Black at bottom"), this::showBoardOptions);
      picker(page, "Side to move", "turn", settings.turn(),
          List.of("Auto", "White", "Black"), this::showBoardOptions);
      picker(page, "Eval bar position", "evaluation_position", settings.evaluationPosition(),
          List.of("Auto", "Top", "Bottom", "Left", "Right", "Custom"), this::showBoardOptions);
    }
    toggle(page, "Predict replies", "predict", true, this::showBoardOptions);
    if (settings.predict())
      number(page, "Prediction length", "prediction_plies", settings.predictionPlies(), 1, 12, 1);
    toggle(page, "Show moves while thinking", "early", true);
    if (host == null) {
      toggle(page, "Steady arrows", "steady", true);
      toggle(page, "Lock move", "lock_move", false);
    }
  }

  private void engine(LinearLayout page, String title, boolean evaluation) {
    EngineCatalog.Entry selected = EngineCatalog.get(evaluation ? settings.evaluator() : settings.engine());
    button(page, title + " · " + selected.name(), () -> {
      LinearLayout choices = page(this::showEngines);
      choices.addView(ui.text(title, 15, MobileUi.FG, true));
      choices.addView(ui.text(EngineProfiles.description(context, selected), 13, MobileUi.MUTED, false));
      List<EngineCatalog.Entry> engines = new ArrayList<>();
      for (var entry : EngineCatalog.ALL) {
        if ((!evaluation || !entry.tiny()) && EngineCatalog.ready(context, entry.id())) engines.add(entry);
      }
      if (engines.isEmpty()) choices.addView(ui.text("No compatible engines installed.", 14, MobileUi.MUTED, false));
      for (var entry : engines) button(choices, entry.name(), () -> {
        settings.p.edit().putString(evaluation ? "evaluator" : "engine", entry.id()).apply();
        showEngines();
      });
    });
  }

  private void picker(LinearLayout page, String label, String key, String current, List<String> names, Runnable back) {
    button(page, label + " · " + current, () -> {
      LinearLayout options = page(back);
      options.addView(ui.text(label, 15, MobileUi.FG, true));
      for (String name : names) button(options, name, () -> {
        settings.p.edit().putString(key, name).apply();
        back.run();
      });
    });
  }

  private void toggle(LinearLayout page, String label, String key, boolean fallback) {
    toggle(page, label, key, fallback, () -> {});
  }

  private void toggle(LinearLayout page, String label, String key, boolean fallback, Runnable after) {
    Switch setting = new Switch(context);
    setting.setText(label);
    setting.setTextSize(14);
    setting.setTextColor(MobileUi.FG);
    setting.setPadding(ui.dp(4), 0, ui.dp(4), 0);
    setting.setGravity(Gravity.CENTER_VERTICAL);
    int[][] state = {{android.R.attr.state_checked}, {}};
    setting.setThumbTintList(new ColorStateList(state, new int[] {ACCENT, MUTED}));
    setting.setTrackTintList(new ColorStateList(state, new int[] {0xff7657aa, BORDER}));
    setting.setChecked(settings.p.getBoolean(key, fallback));
    setting.setOnCheckedChangeListener((button, value) -> {
      settings.p.edit().putBoolean(key, value).apply();
      after.run();
    });
    page.addView(setting, new LinearLayout.LayoutParams(-1, ui.dp(48)));
  }

  private void number(LinearLayout page, String label, String key, int value, int min, int max, int step) {
    page.addView(ui.text(label, 14, MobileUi.MUTED, false));
    page.addView(new MobileUi.Stepper(ui, min, max, value, step, next ->
        settings.p.edit().putInt(key, next).apply()));
  }

  private void time(LinearLayout page, String label, String key, float seconds, float min) {
    button(page, label + " · " + String.format(Locale.ROOT, "%.2f s", seconds), () -> {
      LinearLayout controls = page(this::showEngines);
      controls.addView(ui.text(label, 15, MobileUi.FG, true));
      for (float preset : new float[] {min, .1f, .25f, .5f, 1f, 2f, 5f, 10f, 30f}) {
        button(controls, String.format(Locale.ROOT, "%.2f s", preset),
            () -> saveTime(key, preset));
      }
      controls.addView(ui.text("Custom time · hundredths of a second", 13, MobileUi.MUTED, false));
      MobileUi.Stepper custom = new MobileUi.Stepper(ui, Math.round(min * 100), 3000,
          Math.round(seconds * 100), ignored -> {});
      controls.addView(custom);
      button(controls, "Apply custom time", () -> saveTime(key, custom.getValue() / 100f));
    });
  }

  private void saveTime(String key, float seconds) {
    settings.p.edit().putFloat(key, seconds).apply();
    showEngines();
  }
}
