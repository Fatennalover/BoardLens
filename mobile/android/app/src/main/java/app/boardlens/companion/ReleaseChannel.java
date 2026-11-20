package app.boardlens.companion;

import android.content.Context;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

final class ReleaseChannel {
  private ReleaseChannel() {}

  static String repository(Context context) {
    try (InputStream in = context.getAssets().open("release-channel.json")) {
      String repo = new JSONObject(new String(Streams.read(in, 4096), StandardCharsets.UTF_8))
          .optString("repository", "");
      return repo.matches("[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9][A-Za-z0-9_.-]*") ? repo : "";
    } catch (Exception ignored) {
      return "";
    }
  }
}
