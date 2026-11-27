# BoardLens overhaul verification

## Using the changes

- Open **Board settings → Recognition** to choose Conservative, Balanced, Aggressive, or Custom. Custom settings cover minimum piece confidence, average confidence, grid confidence, matching frames, and scan interval.
- The **All boards** page scrolls as boards are added. Use **Pause** to suspend a board, **Keep** to retain it while it is unavailable, and **Search settings** to choose its engine, limits, priority, and arrow options. **Parallel board searches** controls how many extra boards search at once.
- **Engine suggestions** controls how many first moves are compared. **Lookahead** controls the length of each predicted line and includes the first move. One ply is one side’s move. Two plies make a full move. Search depth controls the engine’s search, while calculation time and lookahead time control its budgets.
- **Coach settings** has independent engine limits, reply and evaluation visibility, and move and reply colors. The Browser Reader requests a separate Coach search when its Coach menu is enabled.
- In **Review game**, select a position, set **First choice** and **Line length**, then select **Play out from here**. Predicted lines remain in the move-list selector. **Stop** preserves the computed moves, and **Extend line** computes another batch. **Analyze game** uses the recorded moves.
- Use **Capture** from Live screen or Screenshot to open an image, capture a display, choose a window, select a board crop, or inspect visible squares. **Freeze frame** copies the confirmed position and move history to the editable screenshot board. **Resume live screen** returns to the original live position. A partial image requires coordinates and orientation. Any reported attacks are geometric observations within the visible squares.

## Findings and changes

| Finding | Cause | Change |
| --- | --- | --- |
| Selecting pieces could hide analysis | Temporary dots and arrows could lower model confidence enough for a tracked read to be discarded. A sequence of rejected frames could lose the target. | Tracked reads can compare previous occupied piece shapes. A frame with the same piece shapes can retain its confirmed position. A genuinely obscured board keeps its last position in the app and hides live overlays until it is readable again. |
| Small or more numerous boards were missed | Discovery used a 160-pixel minimum and returned at most three boards. Other limits independently rejected extra boards in the desktop and browser paths. | Lowered the geometric minimum to 96 pixels, removed the board-count caps, added edge-aligned crop recovery, and retained the shape and chess-position checks. The smallest complete board verified here is 128 pixels square. |
| Larger groups were expensive | Discovery repeatedly sampled candidate grids and matched colors using array-wide sorting. Stable regions and companion cards also discarded their caches when board counts grew. | The checker samples are reused, color bins use counting, and the companion keeps one render cache entry per active board. macOS shares one capture across crops on the same display. Stable live boards can reuse recent results. |
| Board identities could change on focus or DOM changes | Browser board indexes were based on visible list order, focused tab updates cleared other tabs, and the desktop applied several three-board caps. | The browser assigns a stable slot to each element and reports readable boards in other visible browser windows. The desktop queues secondary boards independently and retains modern reader sessions through short disconnects. |
| Secondary-board work could grow with the number of boards | Each extra board opened its own engine process and worker thread. | Extra board analysis uses a bounded pool of reusable UCI sessions, a bounded result cache, priority with wait-time aging, and cancellable per-board requests. Primary, evaluation, and review searches have their own limits. |
| Only the lead move could get a long line | Desktop and Android had separate paths for the lead move and Coach replies. The desktop serializer could also retain a malformed tail. | Each candidate carries a validated line. Missing replies are extended in rounds within the budget, and a shorter line has its own status. Cancelled desktop jobs can restart an engine that fails to stop. Android Coach and recommendation searches share the same continuation code. |
| Browser Coach could show the main analysis engine | The browser was given Coach text formatted from the regular recommendation. | An enabled Browser Coach sends its candidate count and uses the desktop Coach profile with its own scheduled request. Earlier Browser Reader versions retain the older message format. |
| Image analysis could block the interface or select a single board | The screenshot entry point used synchronous single-board recognition. | Capture and import share the live scanner’s recognition class. The screenshot chooser preserves separate editable positions, and partial findings are kept outside engine analysis. |

## Verification and benchmark method

The tests use public fixtures already in the repository and offline positions. No personal screenshots or device identifiers were added. A mounted macOS fixture window was captured by window ID and recognized while a second test window overlapped it. macOS window selection uses ScreenCaptureKit. The Windows selector uses Qt window capture, so covered pixels depend on the visible desktop. [Apple ScreenCaptureKit window filter](https://developer.apple.com/documentation/screencapturekit/sccontentfilter/init(desktopindependentwindow:)) · [Qt window capture behavior](https://doc.qt.io/qt-6/qscreen.html#grabWindow)

| Check | Result |
| --- | --- |
| Desktop test suite | 298 passed on macOS, up from 284 before the overhaul. Coverage includes annotated tracking, unknown turns, cropped images, overlay focus, queue cancellation, Browser Coach, and review branches. |
| Android unit suite and release Java compile | 104 passed. Six optional tests skipped because their Maia model fixtures were unavailable. Release Java compiled. |
| macOS window capture | ScreenCaptureKit captured a real test window overlapped by a second window. BoardLens recognized the exact starting position, orientation, and turn. |
| Chromium Browser Reader fixture | The Reader, Coach, and overlay scripts drew 16 arrows on 16 boards and preserved board identities after DOM reorder. Visible unfocused-window reports went through the fixture's simulated extension transport. The desktop integration tests also accepted 18 boards across two reader window IDs. |
| Phone web companion | Chromium at a mobile viewport paired with a running desktop server. It synchronized four suggestions and drew four differently colored arrows before and after a practice move. |
| Android emulator | A locally signed APK upgraded the existing emulator installation. Selecting a Coach move drew its recommendation and dashed reply. Deselecting it cleared both. Coach and Move Advantage settings opened. |

Run the desktop suite from `desktop` with the installed project dependencies and set `STOCKFISH_EXECUTABLE` to a local Stockfish binary.

```sh
python -m pytest -q
```

Run the Android suite from `mobile/android` with the Android SDK and the JDK configured. The optional real-engine tests use `BOARDLENS_STOCKFISH_TEST_ENGINE` and `BOARDLENS_MAIA_TEST_MODELS`.

```sh
./gradlew :app:testDebugUnitTest :app:compileReleaseJavaWithJavac
```

The desktop benchmark uses the same images, the same Stockfish executable and limits, a warmed recognizer, and 15 trials per case. Run these commands from the repository root. `STOCKFISH_EXECUTABLE` must be an absolute path. The first run imports the prior code from a temporary directory. The second run imports the current code.

```sh
baseline=$(mktemp -d)
git archive 09dc4ec desktop/chess_helper | tar -x -C "$baseline"
PYTHONPATH="$baseline/desktop" python desktop/tools/benchmark_recognition.py --samples 15 --stockfish "$STOCKFISH_EXECUTABLE" > before.json
PYTHONPATH=desktop python desktop/tools/benchmark_recognition.py --samples 15 --stockfish "$STOCKFISH_EXECUTABLE" > after.json
```

Add `--stages` for individual recognition call timings. For real display-region capture on macOS, use `--mac-capture --samples 15` with each `PYTHONPATH` above. This requires Screen Recording permission and prints timings only.

### Desktop measurements

These results were measured on an Apple M4 Pro. Times in the table are milliseconds for median, 95th percentile, and maximum. The full-position cases check the expected placement and orientation. The constructed layouts also require every expected board and no extra detections.

| Image or layout | Before | After | Boards found before → after | Correct trials before → after |
| --- | ---: | ---: | ---: | ---: |
| Chess.com Italian, White orientation | 111.72 / 124.15 / 132.09 | 59.02 / 65.28 / 68.48 | 1 → 1 | 15 → 15 |
| Lichess Italian, Black orientation | 108.95 / 114.59 / 116.99 | 55.10 / 63.27 / 63.29 | 1 → 1 | 15 → 15 |
| Cropped Italian position | 8.82 / 9.95 / 11.91 | 8.71 / 9.04 / 9.06 | 1 → 1 | 15 → 15 |
| Forum page with diagram | 148.93 / 154.53 / 155.96 | 88.49 / 94.15 / 95.00 | 1 → 1 | 15 → 15 |
| Pale blue board | 94.96 / 97.42 / 97.71 | 60.53 / 67.69 / 69.59 | 1 → 1 | 15 → 15 |
| Whole-screen capture | 192.01 / 198.18 / 198.50 | 49.78 / 54.80 / 55.21 | 1 → 1 | 15 → 15 |
| Marble board with queens | 115.94 / 120.18 / 120.71 | 62.97 / 69.82 / 71.70 | 1 → 1 | 15 → 15 |
| Low-confidence Horsey pieces | 208.97 / 218.85 / 220.04 | 104.05 / 110.69 / 112.93 | 0 → 0 | 15 → 15 rejected |
| Cropped starting board | 12.35 / 13.05 / 13.81 | 12.16 / 14.07 / 14.85 | 1 → 1 | 15 → 15 |
| Page without a board | 30.88 / 35.31 / 41.29 | 15.43 / 22.51 / 25.04 | 0 → 0 | 15 → 15 rejected |
| 1 board at 128px | 4.28 / 4.49 / 4.53 | 11.60 / 13.33 / 14.89 | 0 → 1 | 0 → 15 |
| 2 boards at 256px | 56.67 / 62.49 / 64.47 | 36.64 / 39.00 / 40.04 | 2 → 2 | 15 → 15 |
| 3 boards at 256px | 84.75 / 90.73 / 90.97 | 51.07 / 54.49 / 54.62 | 3 → 3 | 15 → 15 |
| 4 boards at 240px | 102.07 / 109.61 / 110.09 | 89.93 / 99.58 / 112.82 | 3 → 4 | 0 → 15 |
| 8 boards at 216px | 161.54 / 166.70 / 168.62 | 266.13 / 273.60 / 273.93 | 3 → 8 | 0 → 15 |
| 16 boards at 192px | 292.54 / 304.60 / 319.61 | 418.87 / 425.04 / 427.71 | 3 → 16 | 0 → 15 |

Recognition used 49.55 → 41.79 process CPU seconds and 26.72 → 21.57 wall seconds over the full sample set. Peak RSS for the benchmark process was 301.8 → 306.8 MiB. At the median, the 16-board case yielded about 10 → 38 recognized boards per second because the newer scan covered all 16 boards.

A second 15-trial run with `--stages` timed the grid, piece-read, and chess-position validation calls within a screenshot scan. This captures the work done on all attempted candidates, including rejected ones. Times are median, 95th percentile, and maximum in milliseconds.

| Screenshot | Stage | Before | After |
| --- | --- | ---: | ---: |
| Chess.com Italian | Grid detection and checks | 98.85 / 106.85 / 107.73 | 44.84 / 54.00 / 57.41 |
| Chess.com Italian | Piece recognition | 10.94 / 14.97 / 15.55 | 10.73 / 12.86 / 14.67 |
| Chess.com Italian | Chess-position validation | 1.19 / 1.60 / 1.79 | 1.19 / 1.27 / 1.29 |
| Whole-screen fixture | Grid detection and checks | 182.60 / 192.41 / 193.11 | 39.97 / 44.13 / 46.93 |
| Whole-screen fixture | Piece recognition | 7.40 / 10.22 / 11.80 | 7.37 / 7.94 / 8.35 |
| Whole-screen fixture | Chess-position validation | 1.39 / 1.59 / 1.86 | 1.38 / 1.43 / 1.43 |

Native macOS capture requested one, two, or eight 256px regions from a single display and verified returned bounds and dimensions. The timing covers capture and pixel transfer and excludes board recognition.

| Capture request | Before | After |
| --- | ---: | ---: |
| 1 region | 38.41 / 57.94 / 58.69 | 37.56 / 58.38 / 58.90 |
| 2 regions | 66.56 / 85.97 / 86.35 | 55.33 / 76.85 / 76.92 |
| 8 regions | 253.74 / 269.48 / 272.63 | 55.61 / 76.48 / 78.96 |

| Stockfish result | Before | After |
| --- | ---: | ---: |
| First valid suggestions | 2.55 / 4.26 / 5.92 | 2.75 / 6.20 / 6.67 |
| Final result with lookahead | 123.01 / 475.28 / 478.83 | 367.06 / 475.72 / 476.63 |

The Stockfish run used three suggestions, a 120 ms root search, eight requested plies, and a 350 ms lookahead budget. The final result took longer at the median while extending all candidates. The initial suggestions still arrived in single-digit milliseconds in these warmed runs.

A separate repeat test completed 96 legal Stockfish results across 16 positions in 0.56 seconds, with at most four active workers and four UCI sessions. The jobs reused cached results where the position and settings matched. The Python process peaked at 113.3 MiB. Engine subprocess memory and sustained uncached throughput were outside that test.

## Remaining work

- Continuous capture of minimized or fully hidden third-party windows is limited by the operating system. A hidden browser tab that stops providing updates becomes unavailable. The verified background case is an accessible window or a visible browser document without focus.
- The desktop board queue has a concurrency limit and per-engine thread and hash options. A whole-application hard memory quota and resource accounting across the main engine, evaluation, Coach, and review remain separate work.
- Partial-board inspection supports manual coordinates and local attacks. Automatic coordinate recovery and combining partially obscured reads into an independently verified full position are still open.
- The overlay entry points share legal move data and retain surface-specific painting. A single cross-platform renderer and all per-board Coach and arrow controls in the phone companion remain open.
- Windows runtime testing requires a Windows session. Android testing used a local emulator because a physical Android device was unavailable. Several simultaneous physical displays, diverse video and 3D themes, and multi-hour CPU and memory behavior need their own test runs. Recognition and capture were measured separately. Overlay paint and recovery latency were outside the timed runs. Process RSS excludes engine subprocesses.

Prioritize a Windows and physical Android capture run, stage-level timing for capture through overlay paint, and an uncached multi-hour engine stress run. Use those measurements to set per-platform resource defaults.

## Modified areas

- Desktop scanning and capture use `app.py`, `capture` consumers in `live.py` and `mac_capture.py`, `recognition.py`, `detection.py`, `vision.py`, `screen_images.py`, `screen_settings.py`, and `widgets.py`.
- Desktop search and analysis use `core.py`, `engine.py`, `coach_engine.py`, `game_review.py`, `multiboard.py`, `move_advantage.py`, and `phone_analysis.py`.
- Integrations use `direct_boards.py`, `phone.py`, `assets/phone/app.js`, and `background.js`, `coach.js`, `content.js`, and `reader.js` in both Browser Reader source trees.
- Android uses `CoachPanel.java`, `FloatingControls.java`, `FrameFingerprint.java`, `LocalEngines.java`, `PhoneSettings.java`, and `ScreenService.java` under the companion package.
- Desktop regression files are `test_board_display_updates.py`, `test_browser_coach.py`, `test_capture_cancellation.py`, `test_direct_boards.py`, `test_fast_tracking.py`, `test_live_v2.py`, `test_multiboard.py`, `test_orientation_and_board_display.py`, `test_overlay_focus.py`, `test_practice_review.py`, and `test_prediction_controls.py` under `desktop/tests`.
- Android regression files are `CoachPanelTest.java`, `FrameFingerprintTest.java`, and `MaiaBudgetTest.java` under the companion test package. The benchmark entry point is `desktop/tools/benchmark_recognition.py`.
