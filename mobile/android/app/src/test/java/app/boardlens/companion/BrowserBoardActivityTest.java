package app.boardlens.companion;

import android.app.Application;
import android.net.Uri;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;

import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = 35, application = Application.class)
public final class BrowserBoardActivityTest {
  @Test public void chessSitesUseTheirOwnLoginPages() {
    assertEquals("https://www.chess.com/login", BrowserBoardActivity
        .browserLogin(Uri.parse("https://www.chess.com/play/computer?example=not-forwarded")).toString());
    assertEquals("https://lichess.org/login", BrowserBoardActivity
        .browserLogin(Uri.parse("https://lichess.org/analysis")).toString());
  }

  @Test public void recognizesGoogleSignInLinks() {
    Uri provider = Uri.parse("https://accounts.google.com/o/oauth2/v2/auth?state=webview-only");
    assertTrue(BrowserBoardActivity.isGoogleSignIn(provider));
    assertTrue(BrowserBoardActivity.isGoogleSignIn(Uri.parse("https://www.chess.com/login/google")));
    assertNull(BrowserBoardActivity.browserLogin(provider));
  }

  @Test public void unrelatedOrInsecureDestinationsAreNotGoogleSignIn() {
    assertFalse(BrowserBoardActivity.isGoogleSignIn(Uri.parse("https://www.chess.com/login")));
    assertFalse(BrowserBoardActivity.isGoogleSignIn(Uri.parse("https://accounts.google.com.example.com/signin")));
    assertFalse(BrowserBoardActivity.isGoogleSignIn(Uri.parse("http://accounts.google.com/signin")));
    assertFalse(BrowserBoardActivity.isGoogleSignIn(Uri.parse("https://accounts.google.com:8443/signin")));
    assertNull(BrowserBoardActivity.browserLogin(Uri.parse("https://unrelated.example/login")));
  }
}
