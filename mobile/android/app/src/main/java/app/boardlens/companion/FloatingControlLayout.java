package app.boardlens.companion;

/** Pixel geometry independent of Android window and capture lifecycles. */
final class FloatingControlLayout {
  record Box(int left, int top, int right, int bottom) {
    int width() { return right - left; }
    int height() { return bottom - top; }
    boolean overlaps(Box other) {
      return left < other.right && right > other.left && top < other.bottom && bottom > other.top;
    }
  }

  static Box fit(Box safe, int x, int y, int width, int height) {
    int w = Math.min(safe.width(), Math.max(1, width));
    int h = Math.min(safe.height(), Math.max(1, height));
    int left = clamp(x, safe.left, safe.right - w);
    int top = clamp(y, safe.top, safe.bottom - h);
    return new Box(left, top, left + w, top + h);
  }

  static Box resize(Box safe, Box origin, int dx, int dy, int minWidth, int minHeight) {
    int right = clamp(origin.right + dx, origin.left + minWidth, safe.right);
    int bottom = clamp(origin.bottom + dy, origin.top + minHeight, safe.bottom);
    // If the window is already near the edge, grow back into the available area.
    return fit(safe, origin.left, origin.top,
        Math.max(minWidth, right - origin.left), Math.max(minHeight, bottom - origin.top));
  }

  static Box dock(Box safe, Box desired, Box board, int gap) {
    if (board == null || !desired.overlaps(board)) return desired;
    int w = desired.width(), h = desired.height();
    Box[] choices = {
        fit(safe, desired.left, board.top - h - gap, w, h),
        fit(safe, desired.left, board.bottom + gap, w, h),
        fit(safe, board.left - w - gap, desired.top, w, h),
        fit(safe, board.right + gap, desired.top, w, h)
    };
    Box best = desired;
    long distance = Long.MAX_VALUE;
    for (Box choice : choices) {
      if (choice.overlaps(board)) continue;
      long cost = Math.abs(choice.left - desired.left) + Math.abs(choice.top - desired.top);
      if (cost < distance) { best = choice; distance = cost; }
    }
    return best;
  }

  static Box dockPanel(Box safe, Box desired, Box board, int gap, int minHeight) {
    Box fitted = dock(safe, desired, board, gap);
    if (board == null || !fitted.overlaps(board)) return fitted;
    int above = board.top - gap - safe.top;
    int below = safe.bottom - board.bottom - gap;
    int height = Math.min(desired.height(), Math.max(above, below));
    if (height < minHeight) return desired;
    int top = below >= above ? board.bottom + gap : board.top - gap - height;
    return fit(safe, desired.left, top, desired.width(), height);
  }

  private static int clamp(int value, int low, int high) {
    return Math.min(high, Math.max(low, value));
  }
}
