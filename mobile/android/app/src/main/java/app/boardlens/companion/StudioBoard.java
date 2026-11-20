package app.boardlens.companion;

import android.content.Context;
import android.graphics.*;
import android.view.View;
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

/** UI-only board. The capture service never draws or animates this view. */
final class StudioBoard extends View {
  private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG | Paint.FILTER_BITMAP_FLAG);
  private final RectF tile = new RectF();
  private final Map<Character,Bitmap> pieces = new HashMap<>();
  private ChessPosition position;
  private boolean whiteBottom = true;

  StudioBoard(Context context) {
    super(context);
    setContentDescription("Recognized chess position");
  }

  void position(ChessPosition next, boolean bottom) {
    if (position == next && whiteBottom == bottom) return;
    boolean first = position == null;
    position = next;
    whiteBottom = bottom;
    if (next != null && pieces.isEmpty()) {
      for (char symbol : "KQRBNPkqrbnp".toCharArray()) {
        String file = (Character.isUpperCase(symbol) ? "w" : "b") + Character.toLowerCase(symbol) + ".png";
        try (var image = getContext().getAssets().open("studio/" + file)) {
          pieces.put(symbol, BitmapFactory.decodeStream(image));
        } catch (IOException ignored) { }
      }
    }
    if (first && next != null && isShown() && android.animation.ValueAnimator.areAnimatorsEnabled()) {
      setAlpha(.68f);
      animate().alpha(1f).setDuration(150).start();
    }
    invalidate();
  }

  @Override protected void onMeasure(int width, int height) {
    int limit = Math.round(500 * getResources().getDisplayMetrics().density);
    int side = Math.min(MeasureSpec.getSize(width), limit);
    setMeasuredDimension(MeasureSpec.getSize(width), side);
  }

  @Override protected void onDraw(Canvas canvas) {
    float side = getHeight(), offset = (getWidth() - side) / 2, cell = side / 8;
    if (position == null || side <= 0) return;
    for (int row = 0; row < 8; row++) {
      for (int col = 0; col < 8; col++) {
        int square = whiteBottom ? (7 - row) * 8 + col : row * 8 + 7 - col;
        tile.set(offset + col * cell, row * cell, offset + (col + 1) * cell, (row + 1) * cell);
        paint.setColor((row + col) % 2 == 0 ? 0xffe2ddeb : 0xff877aab);
        canvas.drawRect(tile, paint);
        Bitmap piece = pieces.get(position.b[square]);
        if (piece != null) {
          tile.inset(cell * .045f, cell * .045f);
          canvas.drawBitmap(piece, null, tile, paint);
        }
      }
    }
  }
}
