package app.boardlens.companion;

import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.widget.*;
import java.util.Locale;
import java.util.function.Consumer;

/** Inline picker usable in the app and in a non-focusable floating window. */
final class ArrowColorPicker {
  private static final String[] PRESETS = {
      "#ffc65c", "#8bbaff", "#ec8be9", "#83e4bb", "#bb9aff", "#ff757c", "#55dded", "#ffffff"
  };
  private static final String[] NAMES = {"Gold", "Blue", "Pink", "Mint", "Purple", "Red", "Cyan", "White"};

  static GradientDrawable swatch(MobileUi ui, String color) {
    GradientDrawable shape = ui.shape(Color.parseColor(color), 6);
    shape.setStroke(ui.dp(1), 0x44ffffff);
    return shape;
  }

  static void add(MobileUi ui, LinearLayout form, String initial, Consumer<String> save) {
    float[] hsv = new float[3];
    Color.colorToHSV(Color.parseColor(initial), hsv);
    TextView preview = ui.text(initial.toUpperCase(Locale.ROOT), 15, Color.BLACK, true);
    preview.setGravity(android.view.Gravity.CENTER);
    form.addView(preview, new LinearLayout.LayoutParams(-1, ui.dp(44)));

    Runnable repaint = () -> {
      int color = Color.HSVToColor(hsv);
      String hex = String.format(Locale.ROOT, "#%06x", color & 0xffffff);
      preview.setText(hex.toUpperCase(Locale.ROOT));
      preview.setBackground(swatch(ui, hex));
      double brightness = Color.red(color) * .299 + Color.green(color) * .587 + Color.blue(color) * .114;
      preview.setTextColor(brightness > 150 ? Color.BLACK : Color.WHITE);
    };
    repaint.run();

    SeekBar[] sliders = new SeekBar[3];
    for (int row = 0; row < 2; row++) {
      LinearLayout colors = new LinearLayout(ui.c);
      for (int col = 0; col < 4; col++) {
        int index = row * 4 + col;
        Button choice = ui.button("", false, () -> {
          Color.colorToHSV(Color.parseColor(PRESETS[index]), hsv);
          for (int i = 0; i < sliders.length; i++) sliders[i].setProgress(Math.round(hsv[i] * (i == 0 ? 1 : 100)));
          repaint.run();
        });
        choice.setMinimumWidth(0);
        choice.setMinWidth(0);
        choice.setBackground(swatch(ui, PRESETS[index]));
        choice.setContentDescription(NAMES[index]);
        var layout = new LinearLayout.LayoutParams(0, ui.dp(44), 1);
        layout.setMargins(ui.dp(3), ui.dp(4), ui.dp(3), ui.dp(2));
        colors.addView(choice, layout);
      }
      form.addView(colors);
    }
    String[] channels = {"Hue", "Saturation", "Brightness"};
    for (int i = 0; i < channels.length; i++) {
      int channel = i;
      form.addView(ui.text(channels[i], 13, MobileUi.MUTED, false));
      SeekBar slider = sliders[i] = new SeekBar(ui.c);
      slider.setMax(i == 0 ? 359 : 100);
      slider.setProgress(Math.round(hsv[i] * (i == 0 ? 1 : 100)));
      slider.setContentDescription(channels[i]);
      form.addView(slider, new LinearLayout.LayoutParams(-1, ui.dp(40)));
      slider.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
        public void onStartTrackingTouch(SeekBar bar) {}
        public void onStopTrackingTouch(SeekBar bar) {}
        public void onProgressChanged(SeekBar bar, int value, boolean user) {
          if (!user) return;
          hsv[channel] = channel == 0 ? value : value / 100f;
          repaint.run();
        }
      });
    }
    form.addView(ui.button("Use color", true, () -> save.accept(preview.getText().toString().toLowerCase(Locale.ROOT))),
        new LinearLayout.LayoutParams(-1, ui.dp(48)));
  }

  private ArrowColorPicker() {}
}
