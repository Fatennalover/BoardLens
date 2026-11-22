package app.boardlens.companion;

import android.content.Context;
import android.graphics.*;
import android.view.View;
import android.view.MotionEvent;
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;
import java.util.List;
import java.util.function.IntConsumer;

/** UI-only board. The capture service never draws or animates this view. */
final class StudioBoard extends View {
  record Arrow(String move, int color, String gain) {
    Arrow(String move, int color) { this(move, color, null); }
  }
  private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG | Paint.FILTER_BITMAP_FLAG);
  private final RectF tile = new RectF();
  private final Map<Character,Bitmap> pieces = new HashMap<>();
  private ChessPosition position;
  private boolean whiteBottom = true;
  private IntConsumer squareClick;
  private int selected = -1;
  private int maxSideDp = 500;
  private List<Arrow> arrows = List.of();

  StudioBoard(Context context) {
    super(context);
    setContentDescription("Recognized chess position");
  }

  void interact(IntConsumer click) {
    squareClick = click;
    setClickable(click != null);
    setContentDescription(click == null ? "Chess position" : "Editable chessboard. Tap a piece, then its destination.");
  }

  void hints(int selectedSquare, List<Arrow> moves) {
    selected = selectedSquare;
    arrows = moves;
    invalidate();
  }

  void maximumSide(int dp) {
    maxSideDp = dp;
    requestLayout();
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
    int limit = Math.round(maxSideDp * getResources().getDisplayMetrics().density);
    int side = Math.min(MeasureSpec.getSize(width), limit);
    setMeasuredDimension(MeasureSpec.getSize(width), side);
  }

  @Override protected void onDraw(Canvas canvas) {
    float side = getHeight(), offset = (getWidth() - side) / 2, cell = side / 8;
    if (position == null || side <= 0) return;
    for (int row = 0; row < 8; row++) {
      for (int col = 0; col < 8; col++) {
        int square = squareAt(row, col);
        tile.set(offset + col * cell, row * cell, offset + (col + 1) * cell, (row + 1) * cell);
        paint.setColor(square == selected ? 0xffffc65c : (row + col) % 2 == 0 ? 0xffe2ddeb : 0xff877aab);
        canvas.drawRect(tile, paint);
        Bitmap piece = pieces.get(position.b[square]);
        if (piece != null) {
          tile.inset(cell * .045f, cell * .045f);
          canvas.drawBitmap(piece, null, tile, paint);
        }
      }
    }
    for (Arrow arrow : arrows) drawArrow(canvas, arrow, offset, cell);
  }

  private int squareAt(int row, int column) {
    return whiteBottom ? (7 - row) * 8 + column : row * 8 + 7 - column;
  }

  @Override public boolean onTouchEvent(MotionEvent event) {
    if (squareClick == null || position == null || getHeight() <= 0) return super.onTouchEvent(event);
    if (event.getAction() != MotionEvent.ACTION_UP) return true;
    float side = getHeight(), offset = (getWidth() - side) / 2;
    float x = event.getX() - offset, y = event.getY();
    if (x >= 0 && y >= 0 && x < side && y < side) {
      performClick();
      squareClick.accept(squareAt((int) (y * 8 / side), (int) (x * 8 / side)));
    }
    return true;
  }

  @Override public boolean performClick() { return super.performClick(); }

  private void drawArrow(Canvas canvas, Arrow arrow, float offset, float cell) {
    int from = ChessPosition.square(arrow.move.substring(0, 2));
    int to = ChessPosition.square(arrow.move.substring(2, 4));
    if (!whiteBottom) { from = 63 - from; to = 63 - to; }
    float x = offset + (from % 8 + .5f) * cell, y = (7 - from / 8 + .5f) * cell;
    float endX = offset + (to % 8 + .5f) * cell, endY = (7 - to / 8 + .5f) * cell;
    float distance = (float) Math.hypot(endX - x, endY - y);
    if (distance == 0) return;
    float dx = (endX - x) / distance, dy = (endY - y) / distance;
    if (arrow.gain != null) {
      float neckX = endX - dx * cell * .25f, neckY = endY - dy * cell * .25f;
      float spread = cell * .12f;
      Path outline = new Path();
      outline.moveTo(x + dx * cell * .18f, y + dy * cell * .18f);
      outline.lineTo(neckX, neckY);
      outline.moveTo(neckX + dy * spread, neckY - dx * spread);
      outline.lineTo(endX, endY);
      outline.lineTo(neckX - dy * spread, neckY + dx * spread);
      paint.setStyle(Paint.Style.STROKE);
      paint.setStrokeJoin(Paint.Join.ROUND);
      paint.setStrokeCap(Paint.Cap.ROUND);
      paint.setColor(0xff1a1527);
      paint.setStrokeWidth(cell * .09f);
      canvas.drawPath(outline, paint);
      paint.setColor(arrow.color);
      paint.setStrokeWidth(cell * .037f);
      canvas.drawPath(outline, paint);
      paint.setStyle(Paint.Style.FILL);
      float cx = (x + endX) / 2, cy = (y + endY) / 2;
      paint.setTypeface(Typeface.DEFAULT_BOLD);
      paint.setTextSize(Math.max(11, cell * .22f));
      float halfWidth = paint.measureText(arrow.gain) / 2 + cell * .12f;
      float halfHeight = paint.getTextSize() * .68f;
      paint.setColor(0xff1a1527);
      canvas.drawRoundRect(cx - halfWidth, cy - halfHeight, cx + halfWidth, cy + halfHeight, 4, 4, paint);
      paint.setColor(0xfff8f4ff);
      canvas.drawText(arrow.gain, cx - paint.measureText(arrow.gain) / 2,
          cy - (paint.ascent() + paint.descent()) / 2, paint);
      return;
    }
    float neckX = endX - dx * cell * .30f, neckY = endY - dy * cell * .30f;
    float spread = cell * .16f;
    paint.setColor(arrow.color);
    paint.setStrokeWidth(cell * .10f);
    paint.setStrokeCap(Paint.Cap.ROUND);
    canvas.drawLine(x, y, neckX, neckY, paint);
    Path tip = new Path();
    tip.moveTo(endX, endY);
    tip.lineTo(neckX + dy * spread, neckY - dx * spread);
    tip.lineTo(neckX - dy * spread, neckY + dx * spread);
    tip.close();
    canvas.drawPath(tip, paint);
  }
}
