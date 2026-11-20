package app.boardlens.companion;
import android.app.Application;import org.json.*;import org.junit.*;import org.junit.runner.RunWith;import org.robolectric.*;import org.robolectric.annotation.*;import static org.junit.Assert.*;
@RunWith(RobolectricTestRunner.class) @Config(sdk=35,application=Application.class)
public class AndroidUpdatesTest {
 private static final String ROOT="https://github.com/example-org/BoardLens/releases";
 private JSONObject release()throws Exception{return new JSONObject("{\"html_url\":\"https://github.com/example-org/BoardLens/releases/tag/android-v1.7.0\",\"assets\":[{\"name\":\"BoardLens-Companion-Android.apk\",\"browser_download_url\":\"https://github.com/example-org/BoardLens/releases/download/android-v1.7.0/BoardLens-Companion-Android.apk\"},{\"name\":\"boardlens-update.json\",\"browser_download_url\":\"https://github.com/example-org/BoardLens/releases/download/android-v1.7.0/boardlens-update.json\"}]}");}
 @Test public void androidReleaseCanBeFoundIndependentlyOfDesktopLatest()throws Exception{assertTrue(AppUpdater.eligible(release(),ROOT));assertFalse(AppUpdater.eligible(release().put("draft",true),ROOT));assertFalse(AppUpdater.eligible(release().put("prerelease",true),ROOT));}
 @Test public void modelOnlyAndForeignDownloadReleasesAreIgnored()throws Exception{JSONObject r=release();r.getJSONArray("assets").remove(0);assertFalse(AppUpdater.eligible(r,ROOT));r=release();r.getJSONArray("assets").getJSONObject(1).put("browser_download_url","https://example.com/manifest.json");assertFalse(AppUpdater.eligible(r,ROOT));}
}
