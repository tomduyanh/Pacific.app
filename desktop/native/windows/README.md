# Windows native capture helper

Streams structured context (active app, window title, selected text) to the
Electron native bridge as newline-delimited JSON.

## Build

Developer Command Prompt for Visual Studio (.NET Framework `csc`):

```bat
csc /target:exe /out:PacificCapture.exe PacificCapture.cs ^
    /reference:UIAutomationClient.dll /reference:UIAutomationTypes.dll
```

The bridge (`desktop/src/native-bridge.js`) auto-detects
`native/windows/PacificCapture.exe` and prefers it over `active-win`.

## Notes

- Selected-text capture uses **UI Automation** (`TextPattern`). Apps that don't
  implement `TextPattern` simply return an empty selection — app + window title
  still work.
- Frames are captured on the Electron side via `desktopCapturer`. To follow the
  plan's **Graphics Capture API** path for higher-fidelity frames, add a frame
  stream here (`Windows.Graphics.Capture`) and forward JPEGs to the backend
  `/api/session/screen/live-tick` endpoint.
- No special permissions are required for window titles; some enterprise
  policies restrict UI Automation across process boundaries.
