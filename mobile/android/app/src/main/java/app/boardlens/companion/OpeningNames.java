package app.boardlens.companion;

import android.content.Context;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.zip.GZIPInputStream;

/** Display-only opening names from the Lichess CC0 opening dataset. */
final class OpeningNames {
  private static Map<String,String> entries;
  private static Map<String,String> byPlacement;

  static synchronized void load(Context context) {
    if (entries != null) return;
    Map<String,String> names = new HashMap<>();
    Map<String,String> placements = new HashMap<>();
    try (var reader = new BufferedReader(new InputStreamReader(
        new GZIPInputStream(context.getAssets().open("openings.tsv.gz")), StandardCharsets.UTF_8))) {
      String line;
      while ((line = reader.readLine()) != null) {
        String[] fields = line.split("\t", 3);
        if (fields.length == 3) {
          String name = fields[1] + " · " + fields[2];
          int castling = fields[0].lastIndexOf(' ');
          names.put(fields[0], name);
          if (castling > 0) placements.merge(fields[0].substring(0, castling), name,
              (old, next) -> old.equals(next) ? old : "");
        }
      }
    } catch (IOException ignored) { }
    byPlacement = Map.copyOf(placements);
    entries = Map.copyOf(names);
  }

  static String find(ChessPosition position) {
    Map<String,String> names = entries;
    if (names == null) return "";
    for (ChessPosition current = position; current != null; current = current.previous()) {
      if (current.full > 40) continue;
      String placement = current.placement() + (current.white ? " w" : " b");
      String key = placement + " " + (current.castle.isEmpty() ? "-" : current.castle);
      String name = names.get(key);
      if (name != null) return name;
      // Captured positions can lack castling history. Accept a unique opening name for the observed pieces and turn.
      String inferred = byPlacement.get(placement);
      if (inferred != null && !inferred.isEmpty()) return inferred;
    }
    return "";
  }

  static String moves(ChessPosition position) {
    List<String> reverse = new ArrayList<>();
    for (ChessPosition current = position; current != null && current.previous() != null; current = current.previous()) {
      ChessPosition before = current.previous();
      reverse.add(before.full + (before.white ? ". " : "… ") + before.notation(current.previousMove()));
    }
    Collections.reverse(reverse);
    return String.join("\n", reverse);
  }
}
