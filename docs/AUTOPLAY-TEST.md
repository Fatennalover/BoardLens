# Desktop autoplay

Autoplay starts off whenever you launch BoardLens. It supports the built-in Practice board, standard Chess.com bot games and standard Lichess Analysis. Android has on-device analysis and arrows.

## Start and stop

1. Load or reload **Browser Reader 3.4** in Chrome or Edge. Enable **Use browser extension** under **Board → Computer screen** and pair it with the key shown there. If you have an older desktop test copy, close it so the regular app can use the browser connection.
2. Start a Chess.com **Play Bots** game or open the standard Lichess **Analysis board**. Wait for BoardLens to mirror the position.
3. Open **Autoplay**, choose **My color** and press **Start autoplay**, then return focus to the board tab. Chess.com supplies your actual playing color even if you flip the board. On Lichess, **My color** uses the current bottom color.
4. Press **Stop autoplay** or use the **Stop** shortcut in **Keys**. On the desktop **Practice** board, you can use autoplay without a browser.

Autoplay remains on between games during this app session. In Practice, **New game** starts the next board. In the browser, open the next supported bot game or analysis board in the same tab. BoardLens waits for the new position and color to be confirmed before continuing.

## Timing and move confirmation

The default **100 ms** delay starts as soon as the engine has a confirmed recommendation. The control accepts **0–10,000 ms** in 1 ms steps. Zero removes the added delay. Engine search, recognizing the position and confirming the move take additional time.

BoardLens checks the exact position, legal destination and side to move before submitting. The reader claims each offered move once. Stop cancels offers that the reader has yet to claim. BoardLens waits for the expected move or a verified immediate bot reply before it can play again. If the connection drops while confirming a move, autoplay pauses. It can retry once after the original permission expires and the same focused board still shows the original position. Leaving the tab pauses autoplay until the selected board returns. The move uses the browser board's controls and leaves your mouse free.

## Orientation and game endings

The pixel readers check visible rank labels when legible, then reconcile legal positions in both orientations. Small, hidden or ambiguous coordinates can still need the existing orientation override. Known move history is retained across a flip or a cancelled drag.

Checkmate/stalemate are recognized from the position. Local OCR also checks visible English result text for resignation, timeout, agreed draws and aborts. It cannot know an invisible server result. The check is throttled and runs separately from board recognition. A new starting position releases the end-of-game hold; **Scan now** explicitly resumes analysis of a final position. Windows result OCR requires an installed Windows OCR language pack.

Android result recognition uses bundled Google ML Kit. Screens and recognized text are processed on the device; Google's SDK can collect device/app diagnostics and usage metrics. See [Google's disclosure](https://developers.google.com/ml-kit/android-data-disclosure) and [ML Kit terms](https://developers.google.com/ml-kit/terms). macOS uses its built-in Vision framework. No game screenshots are recorded by BoardLens.

## Evaluation bar

Enable **Engine → Evaluation bar → Screen evaluation**. Drag the floating bar to move it; use its lower-right grip to resize. Position and size save for the primary desktop bar. **Reset bar position** restores automatic placement. Arrow overlays remain click-through.

Browser Reader 3.4 has its own movable, resizable, animated bar with horizontal and vertical layouts. Reload the unpacked extension and the chess tab after replacing its files. It uses the separately selected evaluation engine and works with arrows turned off. Browser bar placement is saved in extension storage.

## Building

Desktop: `python desktop/packaging/build_native.py --work WORK --out OUT` builds the regular app on the corresponding OS.

Android: build `mobile/android/tiny-runtime/BoardLens.Android.csproj`. Gradle resolves the bundled OCR libraries. Sign and align release APKs as usual.
