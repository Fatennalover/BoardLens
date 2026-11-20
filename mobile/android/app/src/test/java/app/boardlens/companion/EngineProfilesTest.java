package app.boardlens.companion;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.annotation.Config;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = 35, application = android.app.Application.class)
public class EngineProfilesTest {
  @Test public void everyPhoneEngineHasAProfileInTheBundledCatalog() {
    var context = RuntimeEnvironment.getApplication();
    for (var engine : EngineCatalog.ALL) {
      String description = EngineProfiles.description(context, engine);
      assertFalse(engine.name(), description.equals(engine.detail()));
      assertTrue(engine.name(), description.contains("\n\n"));
    }
    assertTrue(EngineProfiles.description(context, EngineCatalog.get("tiny278")).contains("307 competition Elo"));
    assertTrue(EngineProfiles.description(context, EngineCatalog.get("maia1-1500")).contains("1500 human training band"));
    assertTrue(EngineProfiles.description(context, EngineCatalog.get("maia3")).contains("Human-trained"));
  }
}
