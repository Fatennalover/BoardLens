package app.boardlens.companion;

import android.app.Activity;
import android.app.AlertDialog;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

final class CoachPanel {
    static final String PREFERENCE = "coach_moves";
    private static final String[] COUNTS = {"Off", "1 move", "2 moves", "3 moves"};

    private final Activity activity;
    private final PhoneSettings settings;
    private final ScrollView view;
    private final TextView content;

    CoachPanel(Activity activity, MobileUi ui, PhoneSettings settings) {
        this.activity = activity;
        this.settings = settings;
        view = new ScrollView(activity);
        view.setFillViewport(true);
        view.setVisibility(View.GONE);
        LinearLayout card = ui.card();
        card.addView(ui.text("Coach", 16, MobileUi.ACCENT, true));
        ui.gap(card, 4);
        content = ui.text("", 13, MobileUi.FG, false);
        content.setTextIsSelectable(true);
        card.addView(content);
        view.addView(card, new ScrollView.LayoutParams(-1, -2));
    }

    View view() {
        return view;
    }

    int count() {
        return Math.max(0, Math.min(COUNTS.length - 1, settings.p.getInt(PREFERENCE, 0)));
    }

    PhoneSettings withCandidates(PhoneSettings limits) {
        int count = count();
        if (count <= limits.moves() || EngineCatalog.get(limits.engine()).tiny()) return limits;
        return limits.override(Map.of("moves", count));
    }

    void options(Runnable onChanged) {
        new AlertDialog.Builder(activity).setTitle("Coach · Moves to show")
                .setSingleChoiceItems(COUNTS, count(), (dialog, index) -> {
                    settings.p.edit().putInt(PREFERENCE, index).apply();
                    onChanged.run();
                    dialog.dismiss();
                })
                .setNegativeButton("Cancel", null).show();
    }

    void render(ChessPosition board, PhoneEngine.Result result, LocalEngines.Evaluated evaluation,
                boolean showMoves, String waitingMessage) {
        int count = count();
        view.setVisibility(count == 0 ? View.GONE : View.VISIBLE);
        if (count == 0) return;

        String text = notes(board, result, evaluation, count, showMoves, waitingMessage);
        if (!text.contentEquals(content.getText())) content.setText(text);
    }

    static String notes(ChessPosition board, PhoneEngine.Result result, LocalEngines.Evaluated evaluation,
                        int count, boolean showMoves, String waitingMessage) {
        if (board == null) return waitingMessage;
        if (result != null && !board.fen().equals(result.fen())) result = null;
        List<String> rows = new ArrayList<>();
        var header = new StringBuilder(board.white ? "White to move" : "Black to move");
        if (result != null && !result.provider().isEmpty()) {
            header.append(" · ").append(result.provider());
        }
        rows.add(header.toString());
        if (evaluation != null && !evaluation.badge().equals("…")) rows.add(evaluation.text());
        int headerRows = rows.size();
        if (!showMoves) {
            rows.add("Waiting for your side to move.");
        } else if (result != null) {
            List<String> legal = board.legal();
            List<PhoneEngine.Line> lines = result.lines();
            for (PhoneEngine.Line line : lines.subList(0, Math.min(count, lines.size()))) {
                if (legal.contains(line.move())) rows.add(describe(board, line));
            }
        }
        if (rows.size() == headerRows) {
            rows.add(waitingMessage);
        }
        return String.join("\n\n", rows);
    }

    private static String describe(ChessPosition board, PhoneEngine.Line line) {
        String move = line.move();
        ChessPosition after = board.play(move);
        int from = ChessPosition.square(move.substring(0, 2));
        String target = move.substring(2, 4);
        List<String> facts = new ArrayList<>();
        char piece = Character.toLowerCase(board.b[from]);
        if ((piece == 'b' || piece == 'n') && from / 8 == (board.white ? 0 : 7)) {
            facts.add("Develops a minor piece.");
        }
        if (List.of("d4", "e4", "d5", "e5").contains(target)) facts.add("Occupies a central square.");
        if (after.inCheck(after.white)) facts.add("Gives check.");
        if (line.pv().size() > 1 && line.pv().get(0).equals(move)) {
            String reply = line.pv().get(1);
            if (after.legal().contains(reply)) facts.add("Likely reply " + after.notation(reply) + ".");
        }
        String score = MoveAdvantageDialog.score(line, 1);
        String heading = board.notation(move) + ("—".equals(score) ? "" : " · " + score);
        return heading + "\n" + board.simple(move) + (facts.isEmpty() ? "" : "\n" + String.join(" ", facts));
    }
}
