package app.boardlens.companion;

import android.content.Context;
import android.graphics.Color;
import android.os.Handler;
import java.util.*;
import org.json.*;

/** Independent, current-position results from up to three extra engines. */
final class ArrowEngines implements AutoCloseable {
    static final String PREF = "arrow_engines";
    static final String MAIN_COLOR = "main_arrow_color";
    static final int SLOTS = 3;
    static final List<String> MODES = List.of("Time", "Depth", "Time + depth", "Adaptive");
    static final List<String> STYLES = List.of("Balanced", "Aggressive", "Defensive", "Human-like");
    private static final String[] DEFAULT_COLORS = {"#ec8be9", "#83e4bb", "#bb9aff"};

    record Profile(String engine, float seconds, int depth, int moves, int plies, int rating, String mode, String style) {
        PhoneSettings apply(PhoneSettings settings) {
            EngineCatalog.Entry model = EngineCatalog.get(engine);
            return settings.override(Map.ofEntries(Map.entry("engine", engine), Map.entry("threads", 1),
                Map.entry("seconds", seconds), Map.entry("depth", depth), Map.entry("moves", model.tiny() ? 1 : moves),
                Map.entry("predict", plies > 1), Map.entry("prediction_plies", plies),
                Map.entry("prediction_seconds", seconds), Map.entry("rating", rating),
                Map.entry("mode", model.tiny() ? "Time" : mode), Map.entry("style", style)));
        }
    }
    record ColoredMove(String move, int color, String engine){}
    private record Recommendation(String move, String engine){}
    private final LocalEngines[] engines = new LocalEngines[SLOTS];
    private final LatestWorkQueue[] workers = new LatestWorkQueue[SLOTS];
    private final Map<Integer,List<Recommendation>> results = new TreeMap<>();
    private volatile long generation;

    ArrowEngines() {
        for (int i = 0; i < SLOTS; i++) {
            engines[i] = new LocalEngines();
            workers[i] = new LatestWorkQueue("Arrow engine " + (i + 2));
        }
    }

    private static JSONArray stored(PhoneSettings settings) {
        try { return new JSONArray(settings.p.getString(PREF, "[]")); }
        catch (JSONException ignored) { return new JSONArray(); }
    }

    private static JSONObject row(JSONArray entries, int slot) {
        JSONObject item = entries.optJSONObject(slot);
        return item == null ? new JSONObject() : item;
    }

    static Profile profile(PhoneSettings settings, int slot) {
        return readProfile(row(stored(settings), slot));
    }

    private static Profile readProfile(JSONObject item) {
        String mode = item.optString("mode", "Time + depth");
        String style = item.optString("style", "Balanced");
        double seconds = item.optDouble("seconds", .25d);
        return new Profile(item.optString("engine", ""),
            (float)(Double.isFinite(seconds) ? Math.max(.05, Math.min(30, seconds)) : .25),
            bound(item.optInt("depth", 18), 1, 60), bound(item.optInt("moves", 1), 1, 5),
            bound(item.optInt("plies", 2), 1, 12), bound(item.optInt("rating", 1500), 600, 2600),
            MODES.contains(mode) ? mode : "Time + depth", STYLES.contains(style) ? style : "Balanced");
    }

    private static int bound(int value, int low, int high) {
        return Math.max(low, Math.min(high, value));
    }

    static void save(PhoneSettings settings, int slot, String key, Object value) {
        JSONArray entries = stored(settings);
        JSONObject item = row(entries, slot);
        try {
            item.put(key, value);
            entries.put(slot, item);
            settings.p.edit().putString(PREF, entries.toString()).apply();
        } catch (JSONException error) {
            throw new IllegalArgumentException("Invalid arrow engine setting", error);
        }
    }

    private static String colorKey(int slot) { return slot < 0 ? MAIN_COLOR : "arrow_color_" + (slot + 2); }

    static boolean isColorKey(String key) {
        return key != null && (key.equals(MAIN_COLOR) || key.startsWith("arrow_color_"));
    }

    static String color(PhoneSettings settings, int slot) {
        return slot < 0 ? settings.mainColor() : readColor(settings, slot, stored(settings));
    }

    private static String readColor(PhoneSettings settings, int slot, JSONArray legacy) {
        String fallback = validColor(row(legacy, slot).optString("color"), DEFAULT_COLORS[slot]);
        return validColor(settings.p.getString(colorKey(slot), fallback), fallback);
    }

    private static String validColor(String color, String fallback) {
        return color != null && color.matches("#[0-9a-fA-F]{6}") ? color : fallback;
    }

    static void saveColor(PhoneSettings settings, int slot, String color) {
        String valid = validColor(color, null);
        if (valid != null) settings.p.edit().putString(colorKey(slot), valid).apply();
    }

    boolean installsFor(PhoneSettings settings, String changedId) {
        boolean stockfish = changedId.equals("verified");
        JSONArray entries = stored(settings);
        for (int slot = 0; slot < SLOTS; slot++) {
            String id = row(entries, slot).optString("engine", "");
            if (id.isEmpty()) continue;
            EngineCatalog.Entry entry = EngineCatalog.get(id);
            if (stockfish ? entry.kind().equals("stockfish") : entry.id().equals(changedId)) return true;
        }
        return false;
    }

    void request(Context context, ChessPosition board, PhoneSettings settings, Handler owner, Runnable changed) {
        cancel();
        JSONArray entries = stored(settings);
        long token = generation;
        for (int i = 0; i < SLOTS; i++) {
            int slot = i;
            Profile profile = readProfile(row(entries, slot));
            if (profile.engine().isEmpty() || !EngineCatalog.ready(context, profile.engine())) continue;
            PhoneSettings limits = profile.apply(settings);
            LocalEngines engine = engines[slot];
            workers[slot].submit(() -> {
                try {
                    if (token != generation) return;
                    var legal = new HashSet<>(board.legal());
                    String root = board.fen();
                    String name = EngineCatalog.get(profile.engine()).name();
                    engine.recommend(context, board, limits, () -> token == generation, (result, complete) -> {
                        if (!complete || token != generation || !result.fen().equals(root)) return;
                        List<Recommendation> arrows = result.lines().stream().filter(line -> legal.contains(line.move()))
                            .map(line -> new Recommendation(line.move(), name)).collect(java.util.stream.Collectors.toList());
                        owner.post(() -> {
                            if (token != generation) return;
                            synchronized (results) {
                                if (arrows.equals(results.put(slot, arrows))) return;
                            }
                            changed.run();
                        });
                    });
                } catch (Exception ignored) { }
            });
        }
    }

    boolean hasArrows() {
        synchronized (results) {
            for (var arrows : results.values()) if (!arrows.isEmpty()) return true;
            return false;
        }
    }

    List<ColoredMove> arrows(PhoneSettings settings) {
        synchronized (results) {
            if (results.isEmpty()) return List.of();
            JSONArray legacy = stored(settings);
            List<ColoredMove> painted = new ArrayList<>();
            for (var slot : results.entrySet()) {
                int tint = Color.parseColor(readColor(settings, slot.getKey(), legacy));
                for (var arrow : slot.getValue()) painted.add(new ColoredMove(arrow.move(), tint, arrow.engine()));
            }
            return painted;
        }
    }

    void cancel() {
        generation++;
        synchronized (results) { results.clear(); }
        for (LocalEngines engine : engines) engine.cancel();
    }

    @Override public void close() {
        cancel();
        for (int i = 0; i < SLOTS; i++) workers[i].close(engines[i]::close);
    }
}
