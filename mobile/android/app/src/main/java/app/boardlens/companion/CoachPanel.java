package app.boardlens.companion;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Handler;
import android.os.Looper;
import android.widget.ArrayAdapter;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

/** An on-device second opinion with its own engine and temporary move previews. */
final class CoachPanel implements AutoCloseable {
    private static final int MOVE_COLOR = 0xffeab1ff;
    private static final int REPLY_COLOR = 0xff76e3dc;
    private final Activity activity;
    private final MobileUi ui;
    private final PhoneSettings settings;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final LatestWorkQueue worker = new LatestWorkQueue("Coach-engine");
    private final LocalEngines engine = new LocalEngines();
    private final AtomicInteger revision = new AtomicInteger();
    private AlertDialog dialog;
    private StudioBoard preview;
    private LinearLayout cards;
    private TextView status;
    private ChessPosition board;
    private boolean whiteBottom, thinking;
    private PhoneEngine.Result result;
    private String selected = "", error = "";

    CoachPanel(Activity activity, MobileUi ui) {
        this.activity = activity;
        this.ui = ui;
        settings = new PhoneSettings(activity, "local-coach");
    }

    void show(ChessPosition position, boolean bottom) {
        if (dialog != null) return;
        LinearLayout page = ui.column();
        page.setPadding(ui.dp(16), ui.dp(8), ui.dp(16), ui.dp(8));
        preview = new StudioBoard(activity);
        preview.maximumSide(222);
        page.addView(preview);
        status = ui.text("", 14, MobileUi.MUTED, false);
        page.addView(status);
        ui.gap(page, 6);
        cards = ui.column();
        ScrollView scroll = new ScrollView(activity);
        scroll.addView(cards);
        page.addView(scroll, new LinearLayout.LayoutParams(-1, ui.dp(205)));
        dialog = new AlertDialog.Builder(activity).setTitle("Coach").setView(page)
                .setNegativeButton("Close", null).setNeutralButton("Settings…", null).create();
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_NEUTRAL)
                .setOnClickListener(view -> options()));
        dialog.setOnDismissListener(ignored -> {
            dialog = null;
            board = null;
            result = null;
            cancel();
        });
        dialog.show();
        update(position, bottom);
    }

    void update(ChessPosition position, boolean bottom) {
        if (dialog == null) return;
        boolean same = board != null && position != null && board.fen().equals(position.fen());
        boolean flipped = whiteBottom != bottom;
        whiteBottom = bottom;
        if (same) {
            if (flipped) render();
            return;
        }
        if (board == null && position == null) {
            render();
            return;
        }
        board = position;
        analyze();
    }

    private void cancel() {
        revision.incrementAndGet();
        engine.cancel();
        selected = "";
        thinking = false;
    }

    private void analyze() {
        cancel();
        result = null;
        error = "";
        ChessPosition position = board;
        if (position == null || position.legal().isEmpty()) {
            render();
            return;
        }
        if (!EngineCatalog.ready(activity, settings.engine())) {
            error = "Install " + EngineCatalog.get(settings.engine()).name()
                    + " in Engine library, or choose an installed engine in Coach settings.";
            render();
            return;
        }
        PhoneSettings configuration = settings.snapshot().override(Map.of(
                "moves", settings.p.getInt("moves", 3),
                "prediction_plies", settings.p.getInt("prediction_plies", 2),
                "prediction_seconds", settings.p.getFloat("prediction_seconds", .55f)));
        int ticket = revision.get();
        thinking = true;
        render();
        worker.submit(() -> {
            if (ticket != revision.get()) return;
            try {
                PhoneEngine.Result ready = engine.coach(activity.getApplicationContext(), position, configuration,
                        () -> ticket == revision.get(), null);
                main.post(() -> accept(ticket, ready, ""));
            } catch (Exception unavailable) {
                main.post(() -> accept(ticket, null,
                        unavailable.getMessage() == null ? "Coach engine is unavailable." : unavailable.getMessage()));
            }
        });
    }

    private void accept(int ticket, PhoneEngine.Result ready, String failure) {
        if (ticket != revision.get() || dialog == null) return;
        thinking = false;
        result = currentResult(board, ready);
        error = failure;
        render();
    }

    static PhoneEngine.Result currentResult(ChessPosition board, PhoneEngine.Result result) {
        return board != null && result != null && board.fen().equals(result.fen()) ? result : null;
    }

    static String reply(ChessPosition board, PhoneEngine.Line line) {
        if (!board.legal().contains(line.move()) || line.pv().size() < 2
                || !line.pv().get(0).equals(line.move())) return "";
        String reply = line.pv().get(1);
        return board.play(line.move()).legal().contains(reply) ? reply : "";
    }

    private void render() {
        if (dialog == null) return;
        preview.position(board, whiteBottom);
        preview.setVisibility(board == null ? android.view.View.GONE : android.view.View.VISIBLE);
        cards.removeAllViews();
        List<StudioBoard.Arrow> arrows = new ArrayList<>();
        if (board == null) {
            status.setText("Scan or open a board to get suggestions.");
        } else if (result == null || result.lines().isEmpty()) {
            status.setText(!error.isEmpty() ? error : thinking
                    ? "Looking for moves with " + EngineCatalog.get(settings.engine()).name() + "…"
                    : "This position has no suggested moves.");
        } else {
            PhoneEngine.Line lead = result.lines().get(0);
            LocalEngines.Evaluated score = LocalEngines.orient(LocalEngines.score(result.provider(), lead), whiteBottom);
            status.setText(score.text());
            for (PhoneEngine.Line line : result.lines()) {
                String move = line.move();
                if (!board.legal().contains(move)) continue;
                String response = settings.p.getInt("prediction_plies", 2) > 1 ? reply(board, line) : "";
                ChessPosition after = board.play(move);
                boolean active = selected.equals(move);
                LinearLayout row = ui.card();
                if (active) {
                    row.getBackground().setTint(0xff493864);
                    arrows.add(new StudioBoard.Arrow(move, MOVE_COLOR));
                    if (!response.isEmpty()) arrows.add(new StudioBoard.Arrow(response, REPLY_COLOR, true));
                }
                String moveScore = MoveAdvantageDialog.score(line, whiteBottom ? 1 : -1);
                row.addView(ui.text(board.notation(move) + "  " + moveScore, 16, MobileUi.FG, true));
                row.addView(ui.text(board.simple(move), 13, MobileUi.FG, false));
                if (settings.p.getInt("prediction_plies", 2) > 1) {
                    String replyText = !response.isEmpty() ? "Likely reply · " + after.notation(response)
                            : after.legal().isEmpty() ? (after.inCheck(after.white) ? "Checkmate" : "Game ends here")
                            : "No reply within the budget";
                    row.addView(ui.text(replyText, 13, REPLY_COLOR, false));
                }
                if (line.pv().size() > 2 && settings.p.getInt("prediction_plies", 2) > 2) {
                    List<String> moves = new ArrayList<>();
                    ChessPosition position = board;
                    for (String ply : line.pv().subList(0, Math.min(line.pv().size(),
                            settings.p.getInt("prediction_plies", 2)))) {
                        if (!position.legal().contains(ply)) break;
                        moves.add(position.notation(ply));
                        position = position.play(ply);
                    }
                    row.addView(ui.text("Line · " + String.join(" → ", moves), 13, MobileUi.MUTED, false));
                }
                row.setFocusable(true);
                row.setOnClickListener(view -> {
                    selected = selected.equals(move) ? "" : move;
                    render();
                });
                cards.addView(row);
                ui.gap(cards, 6);
            }
        }
        preview.hints(-1, arrows);
    }

    private void options() {
        List<EngineCatalog.Entry> engines = new ArrayList<>();
        for (EngineCatalog.Entry entry : EngineCatalog.ALL) {
            if (EngineCatalog.ready(activity, entry.id())) engines.add(entry);
        }
        if (engines.isEmpty()) engines.add(EngineCatalog.get("stockfish"));
        ScrollView scroll = new ScrollView(activity);
        LinearLayout page = ui.column();
        page.setPadding(ui.dp(20), ui.dp(6), ui.dp(20), ui.dp(12));
        scroll.addView(page);
        String[] names = engines.stream().map(EngineCatalog.Entry::name).toArray(String[]::new);
        String[] modes = {"Time", "Depth", "Time + depth"};
        String[] styles = {"Balanced", "Aggressive", "Defensive", "Human-like"};
        Spinner provider = choices(page, "Coach engine", names, namesIndex(engines));
        Spinner mode = choices(page, "Search limit", modes, Arrays.asList(modes).indexOf(settings.mode()));
        Spinner style = choices(page, "Playing style", styles, Arrays.asList(styles).indexOf(settings.style()));
        EditText seconds = number(page, "Think time · seconds", settings.seconds(), true);
        EditText depth = number(page, "Search depth", settings.depth(), false);
        EditText count = number(page, "Suggestions", settings.p.getInt("moves", 3), false);
        EditText strength = number(page, "Stockfish skill · 20 is full strength", settings.skill(), false);
        EditText rating = number(page, "Human model rating", settings.rating(), false);
        EditText threads = number(page, "CPU threads", settings.threads(), false);
        EditText plies = number(page, "Predicted line length · 1 skips replies", settings.p.getInt("prediction_plies", 2), false);
        EditText replyTime = number(page, "Reply budget · seconds", settings.p.getFloat("prediction_seconds", .55f), true);
        AlertDialog options = new AlertDialog.Builder(activity).setTitle("Coach settings").setView(scroll)
                .setPositiveButton("Save", null).setNegativeButton("Cancel", null).create();
        options.setOnShowListener(ignored -> options.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view -> {
            try {
                settings.p.edit().putString("engine", engines.get(provider.getSelectedItemPosition()).id())
                    .putString("mode", modes[mode.getSelectedItemPosition()])
                    .putString("style", styles[style.getSelectedItemPosition()])
                    .putFloat("seconds", read(seconds, .05f, 30))
                    .putInt("depth", (int)read(depth, 1, 40))
                    .putInt("moves", (int)read(count, 1, 5))
                    .putInt("skill", (int)read(strength, 0, 20))
                    .putInt("rating", (int)read(rating, 600, 2600))
                    .putInt("threads", (int)read(threads, 1, 8))
                    .putInt("prediction_plies", (int)read(plies, 1, 12))
                    .putFloat("prediction_seconds", read(replyTime, .1f, 60)).apply();
                options.dismiss();
                analyze();
            } catch (NumberFormatException invalid) { /* Error is displayed at the field. */ }
        }));
        options.show();
    }

    private int namesIndex(List<EngineCatalog.Entry> entries) {
        for (int i = 0; i < entries.size(); i++) {
            if (entries.get(i).id().equals(settings.engine())) return i;
        }
        return 0;
    }

    private Spinner choices(LinearLayout page, String title, String[] names, int selectedIndex) {
        page.addView(ui.text(title, 13, MobileUi.MUTED, true));
        Spinner field = new Spinner(activity);
        ArrayAdapter<String> values = new ArrayAdapter<>(activity, android.R.layout.simple_spinner_item, names);
        values.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        field.setAdapter(values);
        field.setSelection(Math.max(0, selectedIndex));
        page.addView(field, new LinearLayout.LayoutParams(-1, ui.dp(44)));
        return field;
    }

    private EditText number(LinearLayout page, String title, Number value, boolean decimal) {
        page.addView(ui.text(title, 13, MobileUi.MUTED, true));
        EditText field = new EditText(activity);
        field.setSingleLine(true);
        field.setInputType(decimal ? 8194 : 2);
        field.setText(value.toString());
        page.addView(field, new LinearLayout.LayoutParams(-1, ui.dp(44)));
        return field;
    }

    private static float read(EditText field, float minimum, float maximum) {
        try {
            float value = Float.parseFloat(field.getText().toString());
            if (Float.isFinite(value) && minimum <= value && value <= maximum) return value;
        } catch (NumberFormatException ignored) {}
        field.setError(String.format(Locale.ROOT, "%s–%s", minimum, maximum));
        throw new NumberFormatException();
    }

    @Override public void close() {
        if (dialog != null) dialog.dismiss();
        cancel();
        worker.close(engine::close);
    }
}
