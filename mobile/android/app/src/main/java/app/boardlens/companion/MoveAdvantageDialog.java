package app.boardlens.companion;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.view.View;
import android.view.Gravity;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.HashMap;
import java.util.concurrent.CancellationException;

final class MoveAdvantageDialog implements AutoCloseable {
    private static final String[] LIMITS = {"Time + depth", "Time", "Depth"};
    private final Activity activity;
    private final SharedPreferences preferences;
    private final MobileUi ui;
    private AlertDialog dialog;
    private LinearLayout results;
    private TextView status;
    private LocalEngines engines;
    private LatestWorkQueue worker;
    private ChessPosition position;
    private String fen;
    private volatile int generation;
    private int count;
    private int timeMs, depth;
    private String mode;
    private StudioBoard preview;
    private String scorer;

    MoveAdvantageDialog(Activity activity) {
        this.activity = activity;
        ui = new MobileUi(activity);
        preferences = activity.getSharedPreferences("move_advantage", Activity.MODE_PRIVATE);
    }

    void show(ChessPosition board) {
        if (dialog != null) return;
        List<EngineCatalog.Entry> catalog = new ArrayList<>();
        String savedScorer = preferences.getString("engine", "stockfish");
        int selected = 0;
        for (EngineCatalog.Entry entry : EngineCatalog.ALL) {
            if (entry.tiny()) continue;
            if (!entry.id().equals("stockfish") && !EngineCatalog.ready(activity, entry.id())) continue;
            if (entry.id().equals(savedScorer)) selected = catalog.size();
            catalog.add(entry);
        }
        scorer = catalog.get(selected).id();
        PhoneSettings currentSettings = new PhoneSettings(activity);
        timeMs = preferences.getInt("time_ms", Math.round(currentSettings.evaluationSeconds() * 1000));
        depth = preferences.getInt("depth", currentSettings.evaluationDepth());
        mode = preferences.getString("mode", LIMITS[0]);
        count = Math.max(0, Math.min(6, preferences.getInt("count", 3)));

        ScrollView scroll = new ScrollView(activity);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(ui.backdrop());
        LinearLayout content = ui.column();
        content.setPadding(ui.dp(20), ui.dp(14), ui.dp(20), ui.dp(16));
        scroll.addView(content, new ScrollView.LayoutParams(-1, -2));
        content.addView(ui.text("Moves to compare", 14, MobileUi.MUTED, false));
        content.addView(new MobileUi.Stepper(ui, 0, 6, count, value -> {
            count = value;
            preferences.edit().putInt("count", value).apply();
            compare();
        }));
        LinearLayout advanced = ui.column();
        advanced.setVisibility(View.GONE);
        content.addView(ui.button("Scoring settings", false,
                () -> advanced.setVisibility(advanced.isShown() ? View.GONE : View.VISIBLE)));
        content.addView(advanced);
        String[] enginesList = catalog.stream().map(EngineCatalog.Entry::name).toArray(String[]::new);
        advanced.addView(ui.choice("Scoring engine", enginesList, selected, index -> {
            scorer = catalog.get(index).id();
            preferences.edit().putString("engine", scorer).apply();
            compare();
        }));
        ui.gap(advanced, 8);
        advanced.addView(ui.choice("Search limit", LIMITS, List.of(LIMITS).indexOf(mode), index -> {
            mode = LIMITS[index];
            preferences.edit().putString("mode", mode).apply();
            compare();
        }));
        ui.gap(advanced, 8);
        advanced.addView(ui.text("Time budget (ms)", 14, MobileUi.MUTED, false));
        advanced.addView(new MobileUi.Stepper(ui, 50, 30000, timeMs, 50, value -> {
            timeMs = value;
            preferences.edit().putInt("time_ms", value).apply();
            compare();
        }));
        advanced.addView(ui.text("Depth", 14, MobileUi.MUTED, false));
        advanced.addView(new MobileUi.Stepper(ui, 1, 60, depth, value -> {
            depth = value;
            preferences.edit().putInt("depth", value).apply();
            compare();
        }));
        advanced.addView(ui.toggle("Score arrows", "", preferences.getBoolean("score_arrows", true), enabled -> {
            preferences.edit().putBoolean("score_arrows", enabled).apply(); compare();
        }));
        advanced.addView(ui.toggle("Gains only", "", preferences.getBoolean("gains_only", false), enabled -> {
            preferences.edit().putBoolean("gains_only", enabled).apply(); compare();
        }));
        ui.gap(content, 10);
        status = ui.text("", 14, MobileUi.FG, true);
        content.addView(status);
        results = ui.column();
        content.addView(results);
        preview = new StudioBoard(activity);
        preview.maximumSide(260);
        preview.setContentDescription("Move advantage score arrows");
        preview.setVisibility(android.view.View.GONE);
        content.addView(preview);
        engines = new LocalEngines();
        worker = new LatestWorkQueue("move-advantage");
        dialog = new AlertDialog.Builder(activity).setTitle("Move advantage").setView(scroll)
                .setNeutralButton("Engine library", (d, which) ->
                        activity.startActivity(new Intent(activity, ModelsActivity.class)))
                .setPositiveButton("Done", null).create();
        dialog.setOnDismissListener(d -> release());
        dialog.show();
        position = board;
        fen = board == null ? null : board.fen();
        compare();
    }

    void update(ChessPosition board) {
        if (dialog == null) return;
        String current = board == null ? null : board.fen();
        if (java.util.Objects.equals(current, fen)) return;
        position = board;
        fen = current;
        compare();
    }

    private void compare() {
        int ticket = ++generation;
        engines.cancel();
        results.removeAllViews();
        preview.setVisibility(android.view.View.GONE);
        if (count == 0) {
            status.setText("Choose how many moves to compare.");
            return;
        }
        ChessPosition board = position;
        if (board == null || !board.valid() || board.legal().isEmpty()) {
            status.setText("Waiting for a playable position.");
            return;
        }
        String engine = scorer;
        String name = EngineCatalog.get(engine).name();
        if (!EngineCatalog.ready(activity, engine)) {
            status.setText("Install " + name + " from the Engine library.");
            return;
        }
        status.setText("Comparing moves with " + name + "…");
        int moves = count;
        PhoneSettings settings = new PhoneSettings(activity).snapshot();
        PhoneSettings limits = settings.override(Map.of("engine", engine, "style", "Balanced",
                "predict", false, "moves", 1, "mode", mode, "depth", depth,
                "seconds", timeMs / 1000f, "threads", 1, "skill", 20));
        LocalEngines session = engines;
        worker.submit(() -> {
            try {
                PhoneEngine.Result baseline = session.recommend(activity, board, limits, () -> ticket == generation, null);
                if (baseline.lines().isEmpty()) throw new IllegalStateException("Engine did not score this position.");
                List<PhoneEngine.Line> lines = moves == 1 ? baseline.lines() :
                        session.recommend(activity, board, limits.override(Map.of("moves", moves)),
                                () -> ticket == generation, null).lines();
                PhoneEngine.Line current = baseline.lines().get(0);
                Float expected = null;
                Map<String,Float> after = new HashMap<>();
                if (EngineCatalog.get(engine).policy()) {
                    PhoneSettings evaluate = limits.override(Map.of("evaluator", engine, "evaluation_enabled", true));
                    if (ticket != generation) return;
                    expected = session.evaluate(activity, board, evaluate).whiteShare();
                    for (PhoneEngine.Line line : lines) {
                        if (ticket != generation) return;
                        ChessPosition child = board.play(line.move());
                        if (!child.legal().isEmpty()) after.put(line.move(), session.evaluate(activity, child, evaluate).whiteShare());
                        else after.put(line.move(), child.inCheck(child.white) ? (child.white ? 0f : 1f) : .5f);
                    }
                }
                Float positionScore = expected;
                activity.runOnUiThread(() -> display(ticket, name, board, current, lines, positionScore, after));
            } catch (CancellationException ignored) {
            } catch (Exception error) {
                activity.runOnUiThread(() -> {
                    if (ticket == generation) status.setText(name + " could not score this position.");
                });
            }
        });
    }

    private void display(int ticket, String name, ChessPosition board, PhoneEngine.Line current,
                         List<PhoneEngine.Line> lines, Float expected, Map<String,Float> after) {
        if (ticket != generation) return;
        int sign = board.white ? 1 : -1;
        String baseline = expected == null ? score(current, sign) : percentage(expected, board.white);
        status.setText("Position now · " + baseline + "\n" + name + " · " + (board.white ? "White" : "Black") + " to move");
        results.addView(scoreRow("Move", "After", "Change", MobileUi.MUTED, true));
        List<StudioBoard.Arrow> gains = new ArrayList<>();
        for (PhoneEngine.Line line : lines) {
            Float estimate = after.get(line.move());
            if (estimate == null && line.cp() == null && line.mate() == null) continue;
            String delta = estimate == null ? change(current, line, sign)
                    : String.format(Locale.ROOT, "%+.1f pp", 100 * sign * (estimate - expected));
            String score = estimate == null ? score(line, sign) : percentage(estimate, board.white);
            String label = delta;
            if ("Mate changes".equals(delta)) {
                label = line.mate() == null ? "—" :
                        (line.mate() * sign > 0 ? "+M" : "−M") + Math.abs(line.mate());
            }
            if (!"—".equals(label) && preferences.getBoolean("score_arrows", true)
                    && (!preferences.getBoolean("gains_only", false) || label.startsWith("+")))
                gains.add(new StudioBoard.Arrow(line.move(), 0xff53c6df, label));
            int color = delta.startsWith("+") ? 0xff87e4ca : delta.startsWith("-") ? 0xffffb1c5 : MobileUi.MUTED;
            results.addView(scoreRow(board.notation(line.move()), score, delta, color, false));
        }
        if (!gains.isEmpty()) {
            preview.position(board, board.white);
            preview.hints(-1, gains);
            preview.setVisibility(android.view.View.VISIBLE);
        }
        if (results.getChildCount() == 1) status.setText(name + " did not return scored moves.");
    }

    private LinearLayout scoreRow(String move, String after, String change, int color, boolean heading) {
        LinearLayout row = new LinearLayout(activity);
        row.setPadding(ui.dp(8), ui.dp(8), ui.dp(8), ui.dp(8));
        if (!heading && results.getChildCount() % 2 == 1) row.setBackgroundColor(0xff272036);
        TextView first = ui.text(move, 14, heading ? MobileUi.MUTED : MobileUi.FG, true);
        TextView second = ui.text(after, 14, heading ? MobileUi.MUTED : MobileUi.FG, false);
        TextView third = ui.text(change, 14, color, true);
        second.setGravity(Gravity.END);
        third.setGravity(Gravity.END);
        for (TextView field : new TextView[]{first, second, third}) {
            row.addView(field, new LinearLayout.LayoutParams(0, -2, 1));
        }
        return row;
    }

    private static String percentage(float value, boolean white) {
        return String.format(Locale.ROOT, "%.1f%%", 100 * (white ? value : 1f - value));
    }

    static String score(PhoneEngine.Line line, int sign) {
        if (line.mate() != null) {
            return (line.mate() * sign > 0 ? "Mate in " : "Mated in ") + Math.abs(line.mate());
        }
        return line.cp() == null ? "—" : pawns(line.cp() * sign);
    }

    static String change(PhoneEngine.Line current, PhoneEngine.Line candidate, int sign) {
        if (current.mate() != null || candidate.mate() != null) {
            return java.util.Objects.equals(current.mate(), candidate.mate()) ? "—" : "Mate changes";
        }
        if (current.cp() == null || candidate.cp() == null) return "—";
        return pawns((candidate.cp() - current.cp()) * sign);
    }

    private static String pawns(int centipawns) {
        return centipawns == 0 ? "0.00" : String.format(Locale.ROOT, "%+.2f", centipawns / 100.0);
    }

    private void release() {
        ++generation;
        engines.cancel();
        worker.close(engines::close);
        position = null;
        dialog = null;
    }

    @Override public void close() {
        if (dialog != null) dialog.dismiss();
    }
}
