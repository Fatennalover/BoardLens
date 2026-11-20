package app.boardlens.companion;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.json.JSONException;
import org.json.JSONObject;

/** The same profiles used by the desktop engine picker. */
final class EngineProfiles {
  private static JSONObject profiles;

  private static synchronized JSONObject load(Context context) {
    if (profiles != null) return profiles;
    try (var stream = context.getAssets().open("engine-profiles.json")) {
      profiles = new JSONObject(new String(Streams.read(stream, 64 * 1024), StandardCharsets.UTF_8));
    } catch (IOException | JSONException error) {
      android.util.Log.e("BoardLens", "Could not read engine profiles", error);
      profiles = new JSONObject();
    }
    return profiles;
  }

  private static JSONObject data(Context context, EngineCatalog.Entry engine) {
    return load(context).optJSONObject(engine.id());
  }

  static String summary(Context context, EngineCatalog.Entry engine) {
    JSONObject profile = data(context, engine);
    return profile == null ? engine.detail() : profile.optString("style") + " · " + profile.optString("strength");
  }

  static String description(Context context, EngineCatalog.Entry engine) {
    JSONObject profile = data(context, engine);
    if (profile == null) return engine.detail();
    return summary(context, engine) + "\n" + profile.optString("rating") + "\n\n" + profile.optString("description");
  }

  static void show(Activity activity, EngineCatalog.Entry engine) {
    new AlertDialog.Builder(activity).setTitle(engine.name()).setMessage(description(activity, engine))
        .setPositiveButton("Done", null).show();
  }
}
