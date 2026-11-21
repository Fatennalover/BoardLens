package app.boardlens.companion;

import android.app.Application;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.ImageButton;
import android.widget.LinearLayout;
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
  @Test public void browserMenuWorksInItsOwnViewWithoutOverlayPermission() {
    Application context = RuntimeEnvironment.getApplication();
    ShadowSettings.setCanDrawOverlays(false);
    PhoneSettings settings = new PhoneSettings(context);
    settings.p.edit().clear().putBoolean(FloatingControls.ENABLED, false).commit();
    FrameLayout browser = new FrameLayout(context);
    View page = new View(context);
    browser.addView(page);
    FloatingControls controls = new FloatingControls(context, settings, new FloatingControls.Actions() {
      public void scan() {}
      public void stop() { fail("Hiding the menu must not stop analysis"); }
      public void geometryChanged() {}
    }, browser);
    try {
      controls.show(true);
      assertEquals(1, browser.getChildCount());
      browser.layout(0, 0, 600, 800);
      controls.displayChanged();
      assertEquals(2, browser.getChildCount());
      assertSame(page, browser.getChildAt(0));
      LinearLayout menu = (LinearLayout) browser.getChildAt(1);
      ((ImageButton) menu.getChildAt(0)).performClick();
      assertTrue(controls.expanded());

      controls.collapse();
      assertEquals(2, browser.getChildCount());
      assertFalse(controls.expanded());
      controls.close();
      assertEquals(1, browser.getChildCount());
      controls.open();
      assertTrue(controls.expanded());
      assertFalse(settings.p.getBoolean(FloatingControls.ENABLED, true));
      assertTrue(settings.p.getBoolean(FloatingControls.BROWSER_ENABLED, false));
    } finally {
      controls.show(false);
      settings.p.edit().clear().commit();
    }
  }

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
