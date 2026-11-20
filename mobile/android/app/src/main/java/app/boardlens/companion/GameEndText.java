package app.boardlens.companion;
import java.util.Locale;
/** Deliberately excludes the ordinary Resign button and generic review/help text. */
final class GameEndText {
  static String reason(String raw){
    String s=raw.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9½/ .-]"," ").replaceAll("\\s+"," ").trim();
    if(s.length()>180)return null;
    if(s.matches(".*\\b(checkmate|stalemate|game over|game aborted|game drawn)\\b.*"))return raw.trim();
    if(s.matches(".*\\b(you|white|black) (won|wins|lost|loses|resigned)\\b.*"))return raw.trim();
    if(s.matches(".*\\b(won|wins|draw|drawn|lost|loss) (by |on |due to )(resignation|timeout|time|agreement|repetition|abandonment|insufficient material|50.move rule).*"))return raw.trim();
    return null;
  }
}
