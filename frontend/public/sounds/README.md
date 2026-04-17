# Scanner audio assets

Placeholder audio files for `QrCameraScanner` (V1.1 Slice 8). Both files are
synthesised AAC-in-`.mp3` containers (~5 KB each) produced with macOS
`afconvert`:

- `scan-ok.mp3` — 200 ms rising tone (800 Hz → 1200 Hz), 20 ms attack/release envelope.
- `scan-error.mp3` — 350 ms descending tone (600 Hz → 300 Hz).

These are intentionally minimal. V1.1 will replace them with proper
sound-designed assets before field-test; see `V1.1-UI-DESIGN-SPEC.md §5.1`
for the exact acoustic spec Jason signed off (single rising "bing" for OK,
descending "buzz" for error).

Do not remove these files without updating `QrCameraScanner.tsx` — the
component's audio kit loads them by fixed path.

## Notes

- Volume is user-configurable via `localStorage` key `scan_audio_volume`
  (default 0.8). Range 0.0–1.0.
- Mute toggle stored in `localStorage` key `scan_audio_muted` (string
  `"true"` / `"false"`; any other value is treated as un-muted).
- Browsers may refuse to `play()` before a user gesture. The component
  swallows the rejected promise — it's progressive enhancement, not
  mandatory feedback.
