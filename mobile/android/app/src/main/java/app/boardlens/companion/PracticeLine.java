package app.boardlens.companion;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** A snapshot plus legal moves, independent of the live scanner. */
final class PracticeLine {
  private final List<ChessPosition> positions = new ArrayList<>();

  PracticeLine(ChessPosition position) {
    this(position, true);
  }

  private PracticeLine(ChessPosition position, boolean includeHistory) {
    positions.add(position);
    for (ChessPosition at = includeHistory ? position.previous() : null; at != null; at = at.previous()) {
      positions.add(at);
    }
    Collections.reverse(positions);
  }

  static PracticeLine fromHere(ChessPosition position) {
    return new PracticeLine(position, false);
  }

  static PracticeLine restore(List<String> saved) {
    PracticeLine line = new PracticeLine(new ChessPosition(saved.get(0)));
    for (int i = 1; i < saved.size(); i++) line.play(saved.get(i));
    return line;
  }

  int size() { return positions.size(); }
  ChessPosition last() { return at(size() - 1); }
  ChessPosition at(int index) { return positions.get(index); }
  String nextMove(int index) { return index + 1 < size() ? at(index + 1).previousMove() : null; }

  boolean play(String move) {
    if (!last().legal().contains(move)) return false;
    positions.add(last().play(move));
    return true;
  }

  boolean undo() {
    if (size() <= 1) return false;
    positions.remove(size() - 1);
    return true;
  }

  boolean setTurn(boolean white) {
    if (last().white == white) return true;
    ChessPosition next = new ChessPosition(last());
    next.white = white;
    next.ep = -1;
    if (!next.valid()) return false;
    positions.clear();
    positions.add(next);
    return true;
  }

  String label(int index) {
    if (index == 0) return "Starting position";
    ChessPosition before = at(index - 1);
    return before.full + (before.white ? ". " : "… ") + before.notation(nextMove(index - 1));
  }

  ArrayList<String> save() {
    ArrayList<String> saved = new ArrayList<>();
    saved.add(at(0).fen());
    for (int i = 1; i < size(); i++) saved.add(at(i).previousMove());
    return saved;
  }

  static String outcome(ChessPosition board, boolean claimDraw) {
    List<String> legal = board.legal();
    if (legal.isEmpty()) {
      if (board.inCheck(board.white)) return (board.white ? "Black" : "White") + " wins · checkmate";
      return "Draw · stalemate";
    }
    if (insufficientMaterial(board)) return "Draw · insufficient material";
    if (board.half >= 150) return "Draw · 75-move rule";
    if (claimDraw && board.half >= 100) return "Draw · 50-move rule";
    if (board.half >= 8) {
      int repetitions = 1;
      String placement = board.placement();
      int ep = effectiveEp(board, legal);
      for (ChessPosition at = board.previous(); at != null; at = at.previous()) {
        if (at.white == board.white && at.castle.equals(board.castle)
            && at.placement().equals(placement)
            && effectiveEp(at, at.ep < 0 ? List.of() : at.legal()) == ep) repetitions++;
        if (at.half == 0) break;
      }
      if (repetitions >= 5 || claimDraw && repetitions >= 3) return "Draw · repetition";
    }
    return "";
  }

  private static int effectiveEp(ChessPosition board, List<String> legal) {
    if (board.ep < 0) return -1;
    for (String move : legal) {
      int from = ChessPosition.square(move.substring(0, 2));
      int to = ChessPosition.square(move.substring(2, 4));
      if (to == board.ep && from % 8 != to % 8 && Character.toLowerCase(board.b[from]) == 'p') return to;
    }
    return -1;
  }

  private static boolean insufficientMaterial(ChessPosition board) {
    int minors = 0, bishops = 0, squareColor = -1;
    for (int i = 0; i < board.b.length; i++) {
      switch (Character.toLowerCase(board.b[i])) {
        case 'p', 'r', 'q' -> { return false; }
        case 'n' -> minors++;
        case 'b' -> {
          minors++;
          bishops++;
          int color = (i / 8 + i % 8) % 2;
          if (squareColor >= 0 && color != squareColor) return false;
          squareColor = color;
        }
      }
    }
    return minors <= 1 || minors == bishops;
  }
}
