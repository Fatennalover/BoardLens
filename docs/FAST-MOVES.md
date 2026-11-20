# Fast move tracking and screen evaluation

Desktop 2.16.3 and Android 1.8.9.

## Tracking and recommendations

Android's Only my color no longer promotes a predicted reply to an orange current-move arrow. During the opponent's turn it waits; future responses remain explicitly conditional text. Move and evaluation results commit on the capture queue and must match the current position and search generation.

Continuous pixel tracking rejects an unmatched position instead of silently rebuilding it with White to move. Legal one-move and skipped two-ply transitions retain turn/history. A different target, explicit rescan, or direct reader with exact FEN can establish a new position. Pixels alone cannot establish every turn/castling/en-passant fact.

Mobile skipped-move matching skips unchanged piece origins. Desktop requests its second confirming scan after 24 ms instead of relying on the next 75 ms polling tick. Recognition thresholds and chosen engine budgets are unchanged. Uncertain desktop reads hide stale screen arrows immediately.

Cancelled drags and analysis undo restore a recently tracked position with its prior turn, castling and en-passant state. Checkmate and stalemate clear move arrows. Visible result banners for resignations and timeouts with legal moves still present need a separate result signal.

A completed desktop primary recommendation appears before optional continuation searches, even with early suggestions off. Speculative replies never advance the tracked board.

## Evaluation panels

On Android, drag the small score panel itself. Its normalized position saves automatically and stays inside the usable display after rotation. Settings → On-screen display → Eval bar can restore Auto or edge placement. Only this panel receives touches; the board-size arrow window stays non-focusable and touch-through. Capture reads pause during dragging so the reader does not hide the handle mid-drag. Evaluation Off still unloads its engine.

On desktop, enable Engine → Evaluation bar → Screen evaluation. This is independent of Screen arrows and uses the separately selected evaluation engine. The click-through panel sits beside the board, with a horizontal fallback when space is limited. Mac uses a non-activating AppKit panel. Both panels animate new values over 200 ms and retain their previous fill while the next score is pending.

## Verification

- 210 desktop tests passed: transition/history preservation, rejecting unmatched reads, early-off completed recommendations, panel flags and score continuity.
- 85 Android tests passed with real Maia and Stockfish checks, zero skipped; release lint and complete .NET APK build passed. Coverage includes fast single/skipped moves, stale root results, conditional-arrow suppression, bar dragging, safe bounds and restored placement.
- The installed signed Mac launcher ran the new code in an isolated self-test: bundled recognition succeeded, Stockfish 19 returned a legal move, and the native evaluation panel was visible, ignored mouse events, could not become key/main and left foreground focus unchanged. The signed host was not replaced.
- Android emulator installation succeeded. Live offline checks verified a dragged screen bar, touch-through board moves, no orange player arrow on the opponent turn, and restoration of White hints after putting the moved pawn back. A live four-move Fool's Mate also reported Game over / Checkmate and cleared arrows. See the mobile report for limits. No Android device is connected for this version, so no new Android device latency or all-day stability claim is made. No human match or invitation is part of these tests.

Desktop 2.16.6 / Android 1.8.10 additionally read visible rank labels and reconcile flips with legal history. Local result-banner OCR covers visible English resignation/timeout/draw text; an invisible server result remains unknown. See AUTOPLAY-TEST.md for the separate test edition, OCR platform requirements and current validation boundaries.
