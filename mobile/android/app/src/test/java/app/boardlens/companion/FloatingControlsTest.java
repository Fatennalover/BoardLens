package app.boardlens.companion;

import android.app.Application;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.annotation.Config;
import org.robolectric.shadows.ShadowSettings;

import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = 35, application = Application.class)
public final class FloatingControlsTest {
  @Test public void minimizingKeepsTheLogoAndClosingRequiresAnExplicitReopen() {
    Application context = RuntimeEnvironment.getApplication();
    ShadowSettings.setCanDrawOverlays(true);
    PhoneSettings settings = new PhoneSettings(context);
    settings.p.edit().clear().commit();
    FloatingControls controls = new FloatingControls(context, settings, new FloatingControls.Actions() {
      public void scan() {}
      public void stop() { fail("Hiding the menu must not stop scanning"); }
      public void geometryChanged() {}
    });
    try {
      controls.show(true);
      assertFalse(controls.expanded());
      controls.open();
      assertTrue(controls.expanded());
      controls.collapse();
      assertFalse(controls.expanded());
      assertTrue(settings.p.getBoolean(FloatingControls.ENABLED, false));

      controls.close();
      controls.show(false);
      controls.show(true);
      assertFalse(controls.expanded());
      assertFalse(settings.p.getBoolean(FloatingControls.ENABLED, true));

      controls.show(false);
      controls.open();
      assertFalse(controls.expanded());
      assertTrue(settings.p.getBoolean(FloatingControls.ENABLED, false));
      controls.show(true);
      assertTrue(controls.expanded());
    } finally {
      controls.show(false);
    }
  }
}
