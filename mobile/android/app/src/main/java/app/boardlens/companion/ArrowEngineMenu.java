package app.boardlens.companion;

import android.app.Activity;
import android.app.AlertDialog;
import android.text.TextUtils;
import android.view.Gravity;
import android.widget.*;
import java.util.List;
import java.util.Locale;
import java.util.function.Consumer;

/** Shared editor for Android Settings, the live floating panel and the browser reader. */
final class ArrowEngineMenu {
  private final MobileUi ui;
  private final PhoneSettings settings;
  private final Runnable exit;
  private final Consumer<LinearLayout> show;

  ArrowEngineMenu(MobileUi ui, PhoneSettings settings, Runnable exit, Consumer<LinearLayout> show) {
    this.ui = ui;
    this.settings = settings;
    this.exit = exit;
    this.show = show;
  }

  static void edit(Activity activity, PhoneSettings settings) {
    MobileUi ui = new MobileUi(activity);
    ScrollView scroll = new ScrollView(activity);
    AlertDialog dialog = new AlertDialog.Builder(activity).setView(scroll)
        .setPositiveButton("Done", null).create();
    ArrowEngineMenu menu = new ArrowEngineMenu(ui, settings, dialog::dismiss, page -> {
      scroll.removeAllViews();
      scroll.addView(page);
      scroll.scrollTo(0, 0);
    });
    menu.overview();
    dialog.show();
  }

  void overview() {
    LinearLayout page = page("Arrow engines", exit);
    colorRow(page, "Main arrow color", -1, () -> color(-1, this::overview));
    for (int slot = 0; slot < ArrowEngines.SLOTS; slot++) {
      int index = slot;
      String id = ArrowEngines.profile(settings, slot).engine();
      String choice = id.isEmpty() ? "Off" : EngineCatalog.get(id).name();
      colorRow(page, "Engine " + (slot + 2) + " · " + choice, slot, () -> profile(index));
    }
  }

  private void profile(int slot) {
    ArrowEngines.Profile current = ArrowEngines.profile(settings, slot);
    boolean off = current.engine().isEmpty();
    EngineCatalog.Entry entry = EngineCatalog.get(current.engine());
    LinearLayout page = page("Engine " + (slot + 2), this::overview);
    button(page, "Engine · " + (off ? "Off" : entry.name()), () -> engines(slot));
    colorRow(page, "Arrow color", slot, () -> color(slot, () -> profile(slot)));
    if (off) return;
    page.addView(ui.text(EngineProfiles.description(ui.c, entry), 13, MobileUi.MUTED, false));
    ui.gap(page, 8);
    if (!entry.tiny() && !entry.policy()) {
      picker(page, slot, "Search limit", "mode", current.mode(), ArrowEngines.MODES);
      if (!current.mode().equals("Time")) number(page, slot, "Depth", "depth", current.depth(), 1, 60, 1);
    }
    if (entry.tiny() || entry.policy() || !current.mode().equals("Depth"))
      button(page, "Thinking time · " + time(current.seconds()), () -> timePicker(slot, current.seconds()));
    if (!entry.tiny()) number(page, slot, "Recommended moves", "moves", current.moves(), 1, 5, 1);
    number(page, slot, "Prediction plies", "plies", current.plies(), 1, 12, 1);
    if (entry.maia() || entry.id().equals("flounder"))
      number(page, slot, "Target Elo", "rating", current.rating(), 600, 2600, 50);
    if (entry.kind().equals("stockfish"))
      picker(page, slot, "Playing style", "style", current.style(), ArrowEngines.STYLES);
  }

  private void engines(int slot) {
    LinearLayout page = page("Choose engine " + (slot + 2), () -> profile(slot));
    button(page, "Off", () -> choose(slot, "engine", ""));
    for (EngineCatalog.Entry engine : EngineCatalog.ALL)
      if (EngineCatalog.ready(ui.c, engine.id())) button(page, engine.name(), () -> choose(slot, "engine", engine.id()));
  }

  private void color(int slot, Runnable back) {
    LinearLayout page = page(slot < 0 ? "Main arrow color" : "Engine " + (slot + 2) + " arrow color", back);
    ArrowColorPicker.add(ui, page, ArrowEngines.color(settings, slot), color -> {
      ArrowEngines.saveColor(settings, slot, color);
      back.run();
    });
  }

  private void timePicker(int slot, float seconds) {
    LinearLayout page = page("Thinking time", () -> profile(slot));
    for (float preset : new float[]{.05f, .1f, .25f, .5f, 1f, 2f, 5f, 10f, 30f})
      button(page, time(preset), () -> choose(slot, "seconds", preset));
    page.addView(ui.text("Custom · hundredths of a second", 13, MobileUi.MUTED, false));
    MobileUi.Stepper custom = new MobileUi.Stepper(ui, 5, 3000, Math.round(seconds * 100), ignored -> {});
    page.addView(custom);
    button(page, "Apply custom time", () -> choose(slot, "seconds", custom.getValue() / 100f));
  }

  private void choose(int slot, String key, Object value) {
    ArrowEngines.save(settings, slot, key, value);
    profile(slot);
  }

  private void picker(LinearLayout page, int slot, String title, String key, String value, List<String> options) {
    button(page, title + " · " + value, () -> {
      LinearLayout choices = page(title, () -> profile(slot));
      for (String option : options) button(choices, option, () -> choose(slot, key, option));
    });
  }

  private void number(LinearLayout page, int slot, String label, String key, int value, int min, int max, int step) {
    page.addView(ui.text(label, 13, MobileUi.MUTED, false));
    page.addView(new MobileUi.Stepper(ui, min, max, value, step, next -> ArrowEngines.save(settings, slot, key, next)));
    ui.gap(page, 5);
  }

  private static String time(float seconds) { return String.format(Locale.ROOT, "%.2f s", seconds); }

  private LinearLayout page(String title, Runnable back) {
    LinearLayout page = ui.column();
    page.setPadding(ui.dp(10), ui.dp(5), ui.dp(10), ui.dp(7));
    page.addView(ui.text(title, 16, MobileUi.FG, true));
    ui.gap(page, 5);
    button(page, "‹ Back", back);
    show.accept(page);
    return page;
  }

  private void colorRow(LinearLayout page, String label, int slot, Runnable action) {
    Button field = button(page, label, action);
    var tint = ArrowColorPicker.swatch(ui, ArrowEngines.color(settings, slot));
    tint.setBounds(0, 0, ui.dp(17), ui.dp(17));
    field.setCompoundDrawablesRelative(tint, null, null, null);
    field.setCompoundDrawablePadding(ui.dp(8));
  }

  private Button button(LinearLayout page, String label, Runnable action) {
    Button button = ui.button(label, false, action);
    button.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
    button.setSingleLine();
    button.setEllipsize(TextUtils.TruncateAt.END);
    var layout = new LinearLayout.LayoutParams(-1, ui.dp(48));
    layout.bottomMargin = ui.dp(4);
    page.addView(button, layout);
    return button;
  }
}
