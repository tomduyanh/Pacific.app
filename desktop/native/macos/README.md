# macOS native capture helper

Streams structured accessibility context (active app, focused window title,
selected text) to the Electron native bridge as newline-delimited JSON.

## Build

```bash
cd desktop/native/macos
mkdir -p build
swiftc AccessibilityHelper.swift -o build/PacificCapture \
  -framework Cocoa -framework ApplicationServices
```

The bridge (`desktop/src/native-bridge.js`) auto-detects
`native/macos/build/PacificCapture` and prefers it over `active-win`.

## Permissions

Grant in **System Settings → Privacy & Security**:

- **Accessibility** — required to read window titles and the current text
  selection via `AXUIElement`. Without it those fields come back empty (the app
  still works from screenshots).
- **Screen Recording** — only needed if you extend this helper with
  ScreenCaptureKit for high-fidelity frames. Today frames are captured on the
  Electron side via `desktopCapturer`.

## Extending to ScreenCaptureKit

The plan calls for ScreenCaptureKit frames + the Accessibility API for text.
This helper implements the text channel. To add the frame channel, capture with
`SCStream`, JPEG-encode, and emit a second stream of
`{"frame_base64": "..."}` lines; have the bridge forward those to the backend's
`/api/session/screen/live-tick` instead of the `desktopCapturer` path.
