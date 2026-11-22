package app.boardlens.companion;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.ColorStateList;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.graphics.ImageDecoder;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.widget.*;

import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** The local board editor and a review of its recorded positions. */
public final class PracticeActivity extends Activity {
  private static final int PICK_SCREENSHOT = 51, MAX_IMAGE_SIDE = 2200, CONTINUATION_PLIES = 100;
  static final String USE_CAPTURE = "use_capture";
  private final ExecutorService worker = Executors.newSingleThreadExecutor();
  private final LocalEngines engines = new LocalEngines();
  private final ArrowEngines extraEngines = new ArrowEngines();
  private final Handler uiHandler = new Handler(Looper.getMainLooper());
  private final Map<Integer, PhoneEngine.Result> analysis = new HashMap<>();
  private final Map<Integer, PhoneEngine.Result> prediction = new HashMap<>();
  private volatile int generation;
  private MobileUi ui;
  private PhoneSettings settings;
  private SharedPreferences preferences;
  private PracticeLine played, continuation;
  private String engineId, continuationEngine = "", notice = "";
  private boolean auto, whiteBottom = true, reviewing, showingContinuation, busy;
  private int selectedSquare = -1, reviewIndex;
  private PhoneEngine.Result suggestion;
  private float practiceShare = .5f;

  private StudioBoard boardView;
  private TextView positionTitle, opening, score, status;
  private ProgressBar evaluation;
  private Button engine, stop, undo, playBest, previous, next, analyze, playOut, continuationTab;
  private ListView moves;
  private MoveAdapter moveAdapter;
  private LinearLayout turnSlot;

  static void open(Context context, boolean scanned) {
    context.startActivity(new Intent(context, PracticeActivity.class).putExtra(USE_CAPTURE, scanned));
  }

  @Override public void onCreate(Bundle saved) {
    super.onCreate(saved);
    ui = new MobileUi(this);
    settings = new PhoneSettings(this);
    preferences = getSharedPreferences("practice-board", MODE_PRIVATE);
    auto = preferences.getBoolean("auto_suggest", true);
    engineId = preferences.getString("engine", EngineCatalog.get(settings.engine()).id());
    OpeningNames.load(this);
    played = new PracticeLine(new ChessPosition(ChessPosition.START_FEN));
    if (saved != null && saved.getStringArrayList("played") != null) {
      played = PracticeLine.restore(saved.getStringArrayList("played"));
      whiteBottom = saved.getBoolean("white_bottom", true);
      reviewing = saved.getBoolean("reviewing");
      ArrayList<String> savedContinuation = saved.getStringArrayList("continuation");
      if (savedContinuation != null) {
        continuation = PracticeLine.restore(savedContinuation);
        continuationEngine = saved.getString("continuation_engine", "Engine continuation");
        showingContinuation = saved.getBoolean("showing_continuation");
      }
      reviewIndex = Math.min(saved.getInt("review_index"), reviewLine().size() - 1);
    } else if (getIntent().getBooleanExtra(USE_CAPTURE, false)) {
      loadScan();
    }
    if (Build.VERSION.SDK_INT >= 33) {
      getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
          android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::goBack);
    }
    show(reviewing);
    if (reviewing) moves.setSelection(reviewIndex);
    else if (auto) suggest();
  }

  private void show(boolean review) {
    reviewing = review;
    ScrollView root = new ScrollView(this);
    LinearLayout page = ui.page(root);
    page.addView(ui.header(review ? "Game review" : "Practice", "Back",
        review ? this::backToPractice : this::finish, null));
    ui.gap(page, 12);

    if (!review) {
      row(page, ui.button("Use scanned board", false, this::useScan),
          ui.button("Open screenshot", false, this::chooseScreenshot));
      ui.gap(page, 8);
      row(page, ui.button("New game", false, this::newGame),
          ui.button("Flip board", false, () -> { whiteBottom = !whiteBottom; render(); }));
      ui.gap(page, 12);
    }
    LinearLayout card = ui.card();
    positionTitle = ui.text("", 17, MobileUi.FG, true);
    opening = ui.text("", 14, MobileUi.ACCENT, false);
    card.addView(positionTitle);
    card.addView(opening);
    if (!review) {
      turnSlot = ui.column();
      ui.gap(card, 8);
      card.addView(turnSlot);
    }
    ui.gap(card, 10);
    boardView = new StudioBoard(this);
    if (review) boardView.maximumSide(286);
    boardView.interact(review ? null : this::tapSquare);
    card.addView(boardView, new LinearLayout.LayoutParams(-1, -2));
    ui.gap(card, 10);
    evaluation = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
    evaluation.setMax(1000);
    evaluation.setProgressTintList(ColorStateList.valueOf(MobileUi.ACCENT));
    evaluation.setProgressBackgroundTintList(ColorStateList.valueOf(MobileUi.BORDER));
    evaluation.setContentDescription("White's evaluation");
    card.addView(evaluation, new LinearLayout.LayoutParams(-1, ui.dp(8)));
    ui.gap(card, 8);
    score = ui.text("", 14, MobileUi.FG, false);
    card.addView(score);
    page.addView(card);
    ui.gap(page, 12);
    status = ui.text("", 14, MobileUi.MUTED, false);
    page.addView(status);
    engine = ui.button("", false, this::chooseEngine);
    stop = ui.button("Stop", false, () -> { cancel(); notice = "Analysis stopped"; render(); });
    if (review) {
      row(page, engine, stop);
      ui.gap(page, 8);
      analyze = ui.button("Analyze game", true, () -> reviewSearch(false));
      playOut = ui.button("Play out from here", false, () -> reviewSearch(true));
      row(page, analyze, playOut);
      ui.gap(page, 10);
      continuationTab = ui.button("Engine continuation", false, () -> selectLine(true));
      row(page, ui.button("Played moves", false, () -> selectLine(false)), continuationTab);
      moves = new ListView(this);
      moves.setChoiceMode(ListView.CHOICE_MODE_SINGLE);
      moves.setNestedScrollingEnabled(true);
      moveAdapter = new MoveAdapter();
      moves.setAdapter(moveAdapter);
      moves.setOnItemClickListener((list, view, position, id) -> selectPosition(position));
      page.addView(moves, new LinearLayout.LayoutParams(-1, ui.dp(140)));
      previous = ui.button("Previous", false, () -> selectPosition(reviewIndex - 1));
      next = ui.button("Next", false, () -> selectPosition(reviewIndex + 1));
      row(page, previous, next);
    } else {
      row(page, engine, ui.button("Engine library", false, this::openModels));
      ui.gap(page, 8);
      row(page, ui.button("Suggest", true, this::suggest), stop);
      ui.gap(page, 4);
      page.addView(ui.toggle("Auto suggest", "", auto, enabled -> {
        auto = enabled;
        preferences.edit().putBoolean("auto_suggest", enabled).apply();
        if (enabled) suggest(); else { cancel(); notice = ""; render(); }
      }));
      page.addView(ui.toggle("Arrows", "", settings.arrows(), enabled -> {
        settings.p.edit().putBoolean("arrows", enabled).apply();
        if (!enabled) extraEngines.cancel();
        render();
        if (enabled && auto) suggest();
      }));
      undo = ui.button("Undo", false, () -> { if (played.undo()) positionChanged(); });
      playBest = ui.button("Play best move", false, () -> {
        if (suggestion != null && !suggestion.lines().isEmpty()) play(suggestion.lines().get(0).move());
      });
      row(page, undo, playBest);
      ui.gap(page, 8);
      page.addView(ui.button("Review game", false, this::openReview));
    }
    ui.gap(page, 8);
    coach = new CoachPanel(this, ui, settings);
    row(page, ui.button("Coach", false, () -> coach.options(() -> {
        render();
        if (!reviewing && coach.count() > 0) suggest();
    })),
        ui.button("Move advantage", false, this::showMoveAdvantage));
    page.addView(coach.view(), new LinearLayout.LayoutParams(-1, ui.dp(182)));
    MobileUi.inset(this, root);
    setContentView(root);
    updateTurn();
    render();
  }

  private void row(LinearLayout page, Button left, Button right) {
    LinearLayout row = new LinearLayout(this);
    row.addView(left, new LinearLayout.LayoutParams(0, -2, 1));
    LinearLayout.LayoutParams end = new LinearLayout.LayoutParams(0, -2, 1);
    end.leftMargin = ui.dp(8);
    row.addView(right, end);
    page.addView(row);
  }

  private void updateTurn() {
    if (reviewing) return;
    turnSlot.removeAllViews();
    turnSlot.addView(ui.choice("Side to move", new String[]{"White", "Black"}, played.last().white ? 0 : 1, index -> {
      boolean side = index == 0;
      if (played.last().white == side) return;
      if (played.setTurn(side)) positionChanged();
      else {
        notice = "That side cannot move first from this position. Check which king is in check.";
        // Let the choice dialog close before replacing its row.
        turnSlot.post(() -> { updateTurn(); render(); });
      }
    }));
  }

  private PracticeLine reviewLine() { return showingContinuation ? continuation : played; }
  private MoveAdvantageDialog moveAdvantage;
  private CoachPanel coach;

  private void showMoveAdvantage() {
    if (moveAdvantage == null) moveAdvantage = new MoveAdvantageDialog(this);
    moveAdvantage.show(position());
  }

  private ChessPosition position() { return reviewing ? reviewLine().at(reviewIndex) : played.last(); }

  private void render() {
    ChessPosition board = position();
    String result = PracticeLine.outcome(board, reviewing && showingContinuation);
    positionTitle.setText(result.isEmpty() ? (board.white ? "White" : "Black") + " to move · move " + board.full : result);
    String name = OpeningNames.find(board);
    opening.setText(name);
    opening.setVisibility(name.isEmpty() ? View.GONE : View.VISIBLE);
    boardView.position(board, whiteBottom);
    PhoneEngine.Result chosen = reviewing ? (showingContinuation ? prediction : analysis).get(reviewIndex) : suggestion;
    List<StudioBoard.Arrow> arrows = new ArrayList<>();
    List<PhoneEngine.Line> lines = chosen == null ? List.of() : chosen.lines();
    String displayed = "";
    float share = reviewing || !result.isEmpty() ? .5f : practiceShare;
    if (result.startsWith("White wins")) share = 1;
    if (result.startsWith("Black wins")) share = 0;
    if (result.isEmpty() && !lines.isEmpty()) {
      PhoneEngine.Line best = lines.get(0);
      String provider = chosen.provider();
      for (EngineCatalog.Entry profile : EngineCatalog.ALL)
        if (profile.id().equals(provider)) { provider = profile.name(); break; }
      LocalEngines.Evaluated evaluated = LocalEngines.score(provider, best);
      share = evaluated.whiteShare();
      if (!reviewing) practiceShare = share;
      displayed = (best.cp() == null && best.mate() == null ? provider : evaluated.text())
          + "\n" + board.simple(best.move()) + " · " + board.notation(best.move());
      if (reviewing && !best.pv().isEmpty()) displayed += "\nEngine line · " + continuationText(board, best.pv());
      int arrowsToShow = Math.min(reviewing ? 1 : settings.moves(), lines.size());
      for (int rank = 0; rank < arrowsToShow; rank++) {
        arrows.add(new StudioBoard.Arrow(lines.get(rank).move(), Color.parseColor(settings.arrowColor(rank))));
      }
    }
    if (reviewing) {
      String recorded = reviewLine().nextMove(reviewIndex);
      if (recorded != null && (lines.isEmpty() || !recorded.equals(lines.get(0).move()))) {
        arrows.add(new StudioBoard.Arrow(recorded, MobileUi.ACCENT));
      }
    } else for (ArrowEngines.ColoredMove move : extraEngines.arrows(settings)) {
      arrows.add(new StudioBoard.Arrow(move.move(), move.color()));
    }
    boardView.hints(reviewing ? -1 : selectedSquare, settings.arrows() ? arrows : List.of());
    evaluation.setVisibility(settings.evaluationEnabled() ? View.VISIBLE : View.GONE);
    evaluation.setProgress(Math.round(share * 1000), true);
    score.setText(displayed);
    coach.render(board, result.isEmpty() ? chosen : null, null, true,
        result.isEmpty() ? (reviewing ? "Analyze this game to get coaching." :
            "Use Suggest to get coaching for this position.") : result);
    score.setVisibility(displayed.isEmpty() ? View.GONE : View.VISIBLE);
    engine.setText(EngineCatalog.get(engineId).name());
    engine.setEnabled(!busy);
    stop.setEnabled(busy);
    status.setText(notice);
    status.setVisibility(notice.isEmpty() || notice.equals(result) ? View.GONE : View.VISIBLE);
    if (reviewing) {
      analyze.setEnabled(!busy);
      playOut.setEnabled(!busy && result.isEmpty());
      continuationTab.setEnabled(continuation != null);
      continuationTab.setContentDescription(showingContinuation
          ? "Engine continuation · " + continuationEngine : "Engine continuation");
      previous.setEnabled(reviewIndex > 0);
      next.setEnabled(reviewIndex + 1 < reviewLine().size());
      moves.setItemChecked(reviewIndex, true);
    } else {
      undo.setEnabled(played.size() > 1);
      playBest.setEnabled(result.isEmpty() && !lines.isEmpty());
    }
  }

  private static String continuationText(ChessPosition board, List<String> pv) {
    List<String> moves = new ArrayList<>();
    for (String move : pv) {
      if (!board.legal().contains(move)) break;
      moves.add(board.notation(move));
      board = board.play(move);
    }
    return String.join(" ", moves);
  }

  private void tapSquare(int square) {
    ChessPosition board = played.last();
    if (!PracticeLine.outcome(board, false).isEmpty()) return;
    if (selectedSquare >= 0) {
      String uci = ChessPosition.name(selectedSquare) + ChessPosition.name(square);
      List<String> promotion = board.legal().stream().filter(move -> move.startsWith(uci) && move.length() == 5)
          .collect(java.util.stream.Collectors.toList());
      if (!promotion.isEmpty()) {
        new AlertDialog.Builder(this).setTitle("Promote pawn")
            .setItems(new String[]{"Queen", "Rook", "Bishop", "Knight"}, (dialog, index) -> {
              if (board == played.last()) play(uci + "qrbn".charAt(index));
            }).show();
        return;
      }
      if (play(uci)) return;
    }
    char piece = board.b[square];
    selectedSquare = piece != '.' && ChessPosition.color(piece) == board.white ? square : -1;
    render();
  }

  private boolean play(String move) {
    if (!played.play(move)) return false;
    positionChanged();
    return true;
  }

  private void positionChanged() {
    cancel();
    selectedSquare = -1;
    suggestion = null;
    continuation = null;
    analysis.clear();
    prediction.clear();
    notice = "";
    updateTurn();
    render();
    if (auto) suggest();
  }

  private void newGame() {
    played = new PracticeLine(new ChessPosition(ChessPosition.START_FEN));
    practiceShare = .5f;
    positionChanged();
  }

  private boolean loadScan() {
    ScreenService.PracticeSnapshot snapshot = ScreenService.lastScannedBoard;
    if (snapshot == null) {
      notice = "Scan a board in Phone screen first.";
      return false;
    }
    played = new PracticeLine(snapshot.position());
    whiteBottom = snapshot.whiteBottom();
    practiceShare = .5f;
    return true;
  }

  private void useScan() {
    if (loadScan()) positionChanged(); else render();
  }

  private void chooseScreenshot() {
    Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("image/*");
    startActivityForResult(intent, PICK_SCREENSHOT);
  }

  @Override protected void onActivityResult(int request, int result, Intent data) {
    super.onActivityResult(request, result, data);
    if (request != PICK_SCREENSHOT || result != RESULT_OK || data == null || data.getData() == null) return;
    Uri image = data.getData();
    String orientation = settings.orientation();
    String side = settings.turn();
    int ticket = begin("Reading screenshot…");
    worker.execute(() -> {
      if (!current(ticket)) return;
      try (BoardReader reader = new BoardReader(this)) {
        Bitmap bitmap = loadImage(image);
        BoardReader.Read read;
        try { read = reader.read(bitmap, null, orientation); }
        finally { bitmap.recycle(); }
        if (read == null) throw new IOException("No complete chessboard found in this screenshot.");
        ChessPosition found = ChessPosition.sync(null, read.placement(), side, true);
        if (found == null) found = ChessPosition.sync(null, read.placement(), "Auto", true);
        if (found == null) throw new IOException("Could not read a legal position from this screenshot.");
        ChessPosition recognized = found;
        onResult(ticket, () -> {
          played = new PracticeLine(recognized);
          whiteBottom = read.whiteBottom();
          practiceShare = .5f;
          positionChanged();
        });
      } catch (Exception error) { fail(ticket, error); }
    });
  }

  private Bitmap loadImage(Uri image) throws IOException {
    if (Build.VERSION.SDK_INT >= 28) {
      return ImageDecoder.decodeBitmap(ImageDecoder.createSource(getContentResolver(), image), (decoder, info, source) -> {
        int width = info.getSize().getWidth(), height = info.getSize().getHeight();
        float scale = Math.min(1f, MAX_IMAGE_SIDE / (float) Math.max(width, height));
        decoder.setTargetSize(Math.max(1, Math.round(width * scale)), Math.max(1, Math.round(height * scale)));
        decoder.setAllocator(ImageDecoder.ALLOCATOR_SOFTWARE);
      });
    }
    BitmapFactory.Options options = new BitmapFactory.Options();
    options.inJustDecodeBounds = true;
    try (var input = getContentResolver().openInputStream(image)) { BitmapFactory.decodeStream(input, null, options); }
    options.inSampleSize = 1;
    while (Math.max(options.outWidth, options.outHeight) / options.inSampleSize > MAX_IMAGE_SIDE) options.inSampleSize *= 2;
    options.inJustDecodeBounds = false;
    try (var input = getContentResolver().openInputStream(image)) {
      Bitmap bitmap = BitmapFactory.decodeStream(input, null, options);
      if (bitmap == null) throw new IOException("Could not open this image.");
      return bitmap;
    }
  }

  private void chooseEngine() {
    List<EngineCatalog.Entry> ready = new ArrayList<>();
    for (EngineCatalog.Entry entry : EngineCatalog.ALL)
      if (EngineCatalog.ready(this, entry.id())) ready.add(entry);
    if (ready.isEmpty()) { openModels(); return; }
    String[] labels = ready.stream().map(EngineCatalog.Entry::name).toArray(String[]::new);
    new AlertDialog.Builder(this).setTitle(reviewing ? "Review engine" : "Practice engine")
        .setItems(labels, (dialog, index) -> {
          engineId = ready.get(index).id();
          preferences.edit().putString("engine", engineId).apply();
          suggestion = null;
          analysis.clear();
          render();
          if (!reviewing && auto) suggest();
        }).setNegativeButton("Cancel", null).show();
  }

  private void openModels() { startActivity(new Intent(this, ModelsActivity.class)); }

  private boolean engineReady() {
    if (EngineCatalog.ready(this, engineId)) return true;
    notice = "Install " + EngineCatalog.get(engineId).name() + " in Engine library, or choose another installed engine.";
    render();
    return false;
  }

  private void suggest() {
    ChessPosition board = played.last();
    if (!PracticeLine.outcome(board, false).isEmpty() || !engineReady()) return;
    PhoneSettings limits = coach.withCandidates(settings.override(Map.of("engine", engineId)));
    int ticket = begin("Analyzing with " + EngineCatalog.get(engineId).name() + "…");
    if (settings.arrows()) {
      extraEngines.request(this, board, limits, uiHandler, () -> {
        if (current(ticket) && !isFinishing()) render();
      });
    }
    worker.execute(() -> {
      if (!current(ticket)) return;
      try {
        PhoneEngine.Result result = engines.recommend(this, board, limits, () -> current(ticket), (update, rootComplete) -> {
          if (rootComplete || limits.early()) onResult(ticket, () -> { suggestion = update; render(); });
        });
        onResult(ticket, () -> { suggestion = result; complete(""); });
      } catch (Exception error) { fail(ticket, error); }
    });
  }

  private void openReview() {
    cancel();
    notice = played.size() == 1 ? "Play out a continuation from this position, or analyze it with the selected engine." : "";
    showingContinuation = false;
    reviewIndex = played.size() - 1;
    show(true);
    moves.setSelection(reviewIndex);
  }

  private void backToPractice() {
    cancel();
    notice = "";
    show(false);
    if (auto && suggestion == null) suggest();
  }

  private void selectPosition(int index) {
    reviewIndex = Math.max(0, Math.min(index, reviewLine().size() - 1));
    moveAdapter.notifyDataSetChanged();
    render();
    moves.smoothScrollToPosition(reviewIndex);
  }

  private void selectLine(boolean simulated) {
    if (simulated && continuation == null) return;
    showingContinuation = simulated;
    reviewIndex = 0;
    moveAdapter.notifyDataSetChanged();
    render();
    moves.setSelection(0);
  }

  private void reviewSearch(boolean simulate) {
    if (!engineReady()) return;
    String name = EngineCatalog.get(engineId).name();
    PhoneSettings limits = coach.withCandidates(
        settings.override(Map.of("engine", engineId, "moves", 1, "predict", false)));
    List<ChessPosition> positions = new ArrayList<>();
    if (simulate) {
      ChessPosition start = position();
      positions.add(start);
      continuation = PracticeLine.fromHere(start);
      continuationEngine = name;
      prediction.clear();
    } else {
      for (int i = 0; i < played.size(); i++) positions.add(played.at(i));
      analysis.clear();
    }
    if (simulate || showingContinuation) selectLine(simulate);
    int ticket = begin("Analyzing with " + name + "…");
    worker.execute(() -> {
      if (!current(ticket)) return;
      try {
        ChessPosition board = positions.get(0);
        String message = simulate ? "Continuation paused after 50 moves" : "Game analysis complete";
        int length = simulate ? CONTINUATION_PLIES : positions.size();
        for (int i = 0; i < length; i++) {
          if (!current(ticket)) return;
          if (!simulate) board = positions.get(i);
          String finished = PracticeLine.outcome(board, simulate);
          if (!finished.isEmpty()) { message = finished; break; }
          PhoneEngine.Result result = engines.recommend(this, board, limits, () -> current(ticket), null);
          if (result.lines().isEmpty()) throw new IOException("The engine returned no move.");
          String move = result.lines().get(0).move();
          if (!board.legal().contains(move)) throw new IOException("The engine returned an illegal move.");
          int index = i;
          onResult(ticket, () -> {
            (simulate ? prediction : analysis).put(index, result);
            if (simulate) { continuation.play(move); moveAdapter.notifyDataSetChanged(); }
            notice = "Analyzed " + (index + 1) + " positions · " + name;
            render();
          });
          if (simulate) {
            board = board.play(move);
            String ended = PracticeLine.outcome(board, true);
            if (!ended.isEmpty()) { message = ended; break; }
          }
        }
        String summary = message;
        onResult(ticket, () -> complete(summary));
      } catch (Exception error) { fail(ticket, error); }
    });
  }

  private class MoveAdapter extends BaseAdapter {
    public int getCount() { return reviewLine().size(); }
    public String getItem(int position) { return reviewLine().label(position); }
    public long getItemId(int position) { return position; }
    public View getView(int position, View recycled, ViewGroup parent) {
      CheckedTextView item = recycled instanceof CheckedTextView view ? view : new CheckedTextView(PracticeActivity.this);
      item.setText(getItem(position));
      item.setTextColor(MobileUi.FG);
      item.setTextSize(16);
      item.setBackground(ui.shape(position == reviewIndex ? 0xff392952 : MobileUi.BG, 8));
      item.setMinHeight(ui.dp(44));
      item.setPadding(ui.dp(12), ui.dp(10), ui.dp(12), ui.dp(10));
      return item;
    }
  }

  private int begin(String message) {
    cancel();
    busy = true;
    notice = message;
    render();
    return generation;
  }

  private boolean current(int ticket) { return ticket == generation; }
  private void onResult(int ticket, Runnable action) {
    runOnUiThread(() -> { if (current(ticket) && !isFinishing()) action.run(); });
  }
  private void complete(String message) { busy = false; notice = message; render(); }
  private void fail(int ticket, Exception error) {
    if (!(error instanceof CancellationException)) {
      onResult(ticket, () -> complete(error.getMessage() == null ? "Could not complete analysis." : error.getMessage()));
    }
  }
  private void cancel() {
    generation++;
    extraEngines.cancel();
    if (busy) engines.cancel();
    busy = false;
  }

  private void goBack() { if (reviewing) backToPractice(); else finish(); }
  @android.annotation.SuppressLint("GestureBackNavigation")
  @Override public void onBackPressed() { goBack(); }
  @Override protected void onStart() { super.onStart(); PhoneUiVisibility.start(this); }
  @Override protected void onStop() { PhoneUiVisibility.stop(this); super.onStop(); }
  @Override protected void onSaveInstanceState(Bundle state) {
    super.onSaveInstanceState(state);
    state.putStringArrayList("played", played.save());
    state.putBoolean("white_bottom", whiteBottom);
    state.putBoolean("reviewing", reviewing);
    state.putInt("review_index", reviewIndex);
    if (continuation != null) {
      state.putStringArrayList("continuation", continuation.save());
      state.putString("continuation_engine", continuationEngine);
      state.putBoolean("showing_continuation", showingContinuation);
    }
  }
  @Override protected void onDestroy() {
    if (moveAdvantage != null) moveAdvantage.close();
    cancel();
    extraEngines.close();
    worker.execute(engines::close);
    worker.shutdown();
    super.onDestroy();
  }
}
