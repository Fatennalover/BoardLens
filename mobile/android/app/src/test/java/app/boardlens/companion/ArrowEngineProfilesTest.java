package app.boardlens.companion;

import android.app.Application;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.annotation.Config;

import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = 35, application = Application.class)
public final class ArrowEngineProfilesTest {
  private PhoneSettings settings() {
    PhoneSettings settings = new PhoneSettings(RuntimeEnvironment.getApplication(), "arrow-profile-test");
    settings.p.edit().clear().commit();
    return settings;
  }

  @Test public void legacyColorsAndSparseSlotsMigrateWithoutOverwritingSettings() {
    PhoneSettings settings = settings();
    settings.p.edit().putString(ArrowEngines.PREF,
        "[{\"engine\":\"stockfish\",\"seconds\":0.5,\"color\":\"#ab1234\"}]").commit();
    assertEquals("#ab1234", ArrowEngines.color(settings, 0));
    assertEquals("", ArrowEngines.profile(settings, 1).engine());
    ArrowEngines.save(settings, 2, "engine", "stockfish");
    ArrowEngines.save(settings, 2, "depth", 42);
    ArrowEngines.save(settings, 2, "mode", "Adaptive");
    String searches = settings.p.getString(ArrowEngines.PREF, "");
    ArrowEngines.saveColor(settings, 2, "#1133bb");
    assertEquals(searches, settings.p.getString(ArrowEngines.PREF, ""));
    assertEquals("#1133bb", ArrowEngines.color(settings, 2));
    assertEquals("#ab1234", ArrowEngines.color(settings, 0));
    assertEquals(.5f, ArrowEngines.profile(settings, 0).seconds(), .001f);
    assertEquals("", ArrowEngines.profile(settings, 1).engine());
    PhoneSettings extra = ArrowEngines.profile(settings, 2).apply(settings);
    assertEquals(42, extra.depth());
    assertEquals("Adaptive", extra.mode());
    assertEquals(1, extra.threads());
    assertEquals(18, settings.depth());
  }

  @Test public void editorExposesAllSlotsAndSavesAnInlineColor() {
    Application app = RuntimeEnvironment.getApplication();
    PhoneSettings settings = settings();
    AtomicReference<View> view = new AtomicReference<>();
    ArrowEngineMenu editor = new ArrowEngineMenu(new MobileUi(app), settings, () -> {}, view::set);
    editor.overview();
    assertNotNull(find(view.get(), "Engine 2 · Off"));
    assertNotNull(find(view.get(), "Engine 3 · Off"));
    find(view.get(), "Engine 4 · Off").performClick();
    find(view.get(), "Arrow color").performClick();
    find(view.get(), "Mint").performClick();
    find(view.get(), "Use color").performClick();
    assertEquals("#83e4bb", ArrowEngines.color(settings, 2));
    assertEquals("#ec8be9", ArrowEngines.color(settings, 0));
  }

  private View find(View root, String label) {
    if (root instanceof TextView text && text.getText().toString().equals(label)) return root;
    if (label.contentEquals(root.getContentDescription() == null ? "" : root.getContentDescription())) return root;
    if (root instanceof ViewGroup group) {
      for (int i = 0; i < group.getChildCount(); i++) {
        View result = find(group.getChildAt(i), label);
        if (result != null) return result;
      }
    }
    return null;
  }
}
