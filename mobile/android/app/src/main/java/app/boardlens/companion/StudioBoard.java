package app.boardlens.companion;

import android.content.Context;
import android.graphics.*;
import android.view.View;
import android.view.MotionEvent;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;
import java.util.List;
import java.util.function.IntConsumer;

/** UI-only board. The capture service never draws or animates this view. */
final class StudioBoard extends View {
  record Arrow(String move, int color, String gain, boolean dashed) {
    Arrow(String move, int color) { this(move, color, null, false); }
    Arrow(String move, int color, String gain) { this(move, color, gain, false); }
    Arrow(String move, int color, boolean dashed) { this(move, color, null, dashed); }
  }
  private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG | Paint.FILTER_BITMAP_FLAG);
  private final RectF tile = new RectF();
  private final List<RectF> scoreBadges = new ArrayList<>();
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
    scoreBadges.clear();
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
      drawScoreArrow(canvas, arrow, x, y, endX, endY, dx, dy, cell);
      return;
    }
    float neckX = endX - dx * cell * .30f, neckY = endY - dy * cell * .30f;
    float spread = cell * .16f;
    paint.setColor(arrow.color);
    paint.setStrokeWidth(cell * .10f);
    paint.setStrokeCap(Paint.Cap.ROUND);
    if (arrow.dashed) paint.setPathEffect(new DashPathEffect(new float[]{cell * .13f, cell * .1f}, 0));
    canvas.drawLine(x, y, neckX, neckY, paint);
    paint.setPathEffect(null);
    Path tip = new Path();
    tip.moveTo(endX, endY);
    tip.lineTo(neckX + dy * spread, neckY - dx * spread);
    tip.lineTo(neckX - dy * spread, neckY + dx * spread);
    tip.close();
    canvas.drawPath(tip, paint);
  }
  private void drawScoreArrow(Canvas canvas, Arrow arrow, float x, float y,
                              float endX, float endY, float dx, float dy, float cell) {
    int dark = 0xff14121e;
    float tipX = endX - dx * cell * .10f, tipY = endY - dy * cell * .10f;
    float tailX = tipX - dx * cell * .27f, tailY = tipY - dy * cell * .27f;
    float startX = x + dx * cell * .16f, startY = y + dy * cell * .16f;
    float spread = cell * .15f;
    float width = Math.max(2, cell * .044f);
    paint.setStrokeCap(Paint.Cap.BUTT);
    paint.setPathEffect(new DashPathEffect(new float[]{cell * .115f, cell * .090f}, 0));
    paint.setColor(dark);
    paint.setStrokeWidth(width + 2.4f);
    canvas.drawLine(startX, startY, tailX, tailY, paint);
    paint.setColor(arrow.color);
    paint.setStrokeWidth(width);
    canvas.drawLine(startX, startY, tailX, tailY, paint);
    paint.setPathEffect(null);

    Path head = new Path();
    head.moveTo(tipX, tipY);
    head.lineTo(tailX - dy * spread, tailY + dx * spread);
    head.lineTo(tailX + dx * cell * .08f, tailY + dy * cell * .08f);
    head.lineTo(tailX + dy * spread, tailY - dx * spread);
    head.close();
    paint.setColor(dark);
    canvas.drawPath(head, paint);
    paint.setColor(arrow.color);
    paint.setStrokeJoin(Paint.Join.ROUND);
    paint.setStyle(Paint.Style.STROKE);
    canvas.drawPath(head, paint);

    float cx = x + (endX - x) * .64f, cy = y + (endY - y) * .64f;
    paint.setTypeface(Typeface.DEFAULT_BOLD);
    paint.setTextSize(Math.max(11, cell * .23f));
    float halfWidth = (paint.measureText(arrow.gain) + Math.max(13, cell * .22f)) / 2;
    float halfHeight = paint.getTextSize() * .68f + 2;
    float halfBadgeWidth = halfWidth + halfHeight * .5f + 1;
    float halfBadgeHeight = halfHeight + 1;
    RectF bounds = new RectF();
    float boardLeft = (getWidth() - getHeight()) / 2f;
    placeBadge: for (float offset : new float[]{0, .8f, -.8f, 1.4f, -1.4f}) {
      for (float shift : new float[]{0, -.20f, .14f, -.37f}) {
        float bx = cx + (endX - x) * shift - dy * halfHeight * 2 * offset;
        float by = cy + (endY - y) * shift + dx * halfHeight * 2 * offset;
        bounds.set(bx - halfBadgeWidth, by - halfBadgeHeight, bx + halfBadgeWidth, by + halfBadgeHeight);
        if (bounds.left < boardLeft || bounds.right > boardLeft + getHeight()
            || bounds.top < 0 || bounds.bottom > getHeight()) continue;
        boolean overlaps = false;
        for (RectF other : scoreBadges) {
          if (RectF.intersects(bounds, other)) {
            overlaps = true;
            break;
          }
        }
        if (!overlaps) {
          cx = bx;
          cy = by;
          scoreBadges.add(bounds);
          break placeBadge;
        }
      }
    }
    Path badge = new Path();
    badge.moveTo(cx - halfWidth, cy - halfHeight);
    badge.lineTo(cx + halfWidth, cy - halfHeight);
    badge.lineTo(cx + halfWidth + halfHeight * .5f, cy);
    badge.lineTo(cx + halfWidth, cy + halfHeight);
    badge.lineTo(cx - halfWidth, cy + halfHeight);
    badge.lineTo(cx - halfWidth - halfHeight * .5f, cy);
    badge.close();
    paint.setStyle(Paint.Style.FILL);
    paint.setColor(dark);
    canvas.drawPath(badge, paint);
    paint.setStyle(Paint.Style.STROKE);
    paint.setColor(arrow.color);
    paint.setStrokeWidth(Math.max(1.3f, cell * .025f));
    canvas.drawPath(badge, paint);
    paint.setStyle(Paint.Style.FILL);
    paint.setColor(0xffffffff);
    canvas.drawText(arrow.gain, cx - paint.measureText(arrow.gain) / 2,
        cy - (paint.ascent() + paint.descent()) / 2, paint);
  }

}
