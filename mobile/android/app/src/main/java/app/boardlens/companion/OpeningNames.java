package app.boardlens.companion;

import android.content.Context;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.zip.GZIPInputStream;

/** Display-only opening names from the Lichess CC0 opening dataset. */
final class OpeningNames {
  private static Map<String,String> entries;

  static synchronized void load(Context context) {
    if (entries != null) return;
    Map<String,String> names = new HashMap<>();
    try (var reader = new BufferedReader(new InputStreamReader(
        new GZIPInputStream(context.getAssets().open("openings.tsv.gz")), StandardCharsets.UTF_8))) {
      String line;
      while ((line = reader.readLine()) != null) {
        String[] fields = line.split("\t", 3);
        if (fields.length == 3) names.put(fields[0], fields[1] + " · " + fields[2]);
      }
    } catch (IOException ignored) { }
    entries = Map.copyOf(names);
  }

  static String find(ChessPosition position) {
    Map<String,String> names = entries;
    if (names == null) return "";
    for (ChessPosition current = position; current != null; current = current.previous()) {
      if (current.full > 40) continue;
      String key = current.placement() + (current.white ? " w " : " b ") +
          (current.castle.isEmpty() ? "-" : current.castle);
      String name = names.get(key);
      if (name != null) return name;
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
