package app.boardlens.companion;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.CancellationException;

final class MoveAdvantageDialog implements AutoCloseable {
    private static final String[] SCORERS = {"stockfish", "lc0"};
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
    private String scorer;

    MoveAdvantageDialog(Activity activity) {
        this.activity = activity;
        ui = new MobileUi(activity);
        preferences = activity.getSharedPreferences("move_advantage", Activity.MODE_PRIVATE);
    }

    void show(ChessPosition board) {
        if (dialog != null) return;
        scorer = preferences.getString("engine", "stockfish");
        int selected = scorer.equals("lc0") ? 1 : 0;
        scorer = SCORERS[selected];
        count = Math.max(0, Math.min(6, preferences.getInt("count", 3)));

        ScrollView scroll = new ScrollView(activity);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(ui.backdrop());
        LinearLayout content = ui.column();
        content.setPadding(ui.dp(20), ui.dp(14), ui.dp(20), ui.dp(16));
        scroll.addView(content, new ScrollView.LayoutParams(-1, -2));
        String[] enginesList = new String[SCORERS.length];
        for (int i = 0; i < SCORERS.length; i++) {
            enginesList[i] = EngineCatalog.get(SCORERS[i]).name();
        }
        content.addView(ui.choice("Scoring engine", enginesList, selected, index -> {
            scorer = SCORERS[index];
            preferences.edit().putString("engine", scorer).apply();
            compare();
        }));
        ui.gap(content, 12);
        content.addView(ui.text("Moves to compare (0 off)", 14, MobileUi.MUTED, false));
        content.addView(new MobileUi.Stepper(ui, 0, 6, count, value -> {
            count = value;
            preferences.edit().putInt("count", value).apply();
            compare();
        }));
        ui.gap(content, 8);
        content.addView(ui.text("Change from the current estimate, in pawns for the side to move.",
                               13, MobileUi.MUTED, false));
        ui.gap(content, 10);
        status = ui.text("", 14, MobileUi.FG, true);
        content.addView(status);
        results = ui.column();
        content.addView(results);
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
                "predict", false, "moves", 1, "mode", "Time + depth", "depth", settings.evaluationDepth(),
                "seconds", settings.evaluationSeconds(), "threads", 1, "skill", 20));
        LocalEngines session = engines;
        worker.submit(() -> {
            try {
                PhoneEngine.Result baseline = session.recommend(activity, board, limits, () -> ticket == generation, null);
                if (baseline.lines().isEmpty()) throw new IllegalStateException("Engine did not score this position.");
                List<PhoneEngine.Line> lines = moves == 1 ? baseline.lines() :
                        session.recommend(activity, board, limits.override(Map.of("moves", moves)),
                                () -> ticket == generation, null).lines();
                PhoneEngine.Line current = baseline.lines().get(0);
                activity.runOnUiThread(() -> display(ticket, name, board, current, lines));
            } catch (CancellationException ignored) {
            } catch (Exception error) {
                activity.runOnUiThread(() -> {
                    if (ticket == generation) status.setText(name + " could not score this position.");
                });
            }
        });
    }

    private void display(int ticket, String name, ChessPosition board, PhoneEngine.Line current,
                         List<PhoneEngine.Line> lines) {
        if (ticket != generation) return;
        int sign = board.white ? 1 : -1;
        status.setText(name + " · " + (board.white ? "White" : "Black") + " to move\nCurrent " + score(current, sign));
        for (PhoneEngine.Line line : lines) {
            if (line.cp() == null && line.mate() == null) continue;
            ui.gap(results, 7);
            results.addView(ui.text(board.notation(line.move()) + "   " + score(line, sign)
                    + " after   " + change(current, line, sign) + " change", 15, MobileUi.FG, false));
        }
        if (results.getChildCount() == 0) status.setText(name + " did not return scored moves.");
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
