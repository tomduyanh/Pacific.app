// Pacific — macOS native capture helper (Subsystem A).
//
// Streams newline-delimited JSON on stdout whenever the frontmost application or
// window changes:
//
//   {"app_name":"Safari","window_title":"Inbox — Gmail","selected_text":"..."}
//
// It uses:
//   • NSWorkspace frontmost-app notifications + Accessibility API (AXUIElement)
//     for the focused window title and the user's current text selection.
//   • (Frames are captured on the Electron side via desktopCapturer; this helper
//     is purely the structured-text channel. For higher-fidelity frames, wire in
//     ScreenCaptureKit here and emit base64 frames on a second stream.)
//
// Permissions required (System Settings → Privacy & Security):
//   • Accessibility  — to read AXUIElement window titles and selected text.
//   • Screen Recording — only if you extend this helper with ScreenCaptureKit.
//
// Build:
//   swiftc AccessibilityHelper.swift -o build/PacificCapture \
//     -framework Cocoa -framework ApplicationServices
//
// The Electron native bridge auto-detects native/macos/build/PacificCapture.

import Cocoa
import ApplicationServices

func axString(_ element: AXUIElement, _ attr: String) -> String? {
    var value: AnyObject?
    let err = AXUIElementCopyAttributeValue(element, attr as CFString, &value)
    guard err == .success else { return nil }
    return value as? String
}

func focusedWindowTitle(forPID pid: pid_t) -> String {
    let appElement = AXUIElementCreateApplication(pid)
    var win: AnyObject?
    guard AXUIElementCopyAttributeValue(appElement, kAXFocusedWindowAttribute as CFString, &win) == .success,
          let window = win else { return "" }
    return axString(window as! AXUIElement, kAXTitleAttribute as String) ?? ""
}

func focusedSelectedText(forPID pid: pid_t) -> String {
    let appElement = AXUIElementCreateApplication(pid)
    var focused: AnyObject?
    guard AXUIElementCopyAttributeValue(appElement, kAXFocusedUIElementAttribute as CFString, &focused) == .success,
          let element = focused else { return "" }
    return axString(element as! AXUIElement, kAXSelectedTextAttribute as String) ?? ""
}

func emit(app: String, title: String, selection: String) {
    let obj: [String: String] = [
        "app_name": app,
        "window_title": title,
        "selected_text": String(selection.prefix(800)),
    ]
    if let data = try? JSONSerialization.data(withJSONObject: obj),
       let line = String(data: data, encoding: .utf8) {
        print(line)
        fflush(stdout)
    }
}

// Warn (to stderr) if Accessibility permission is missing — titles/selection
// will come back empty until the user grants it.
if !AXIsProcessTrusted() {
    FileHandle.standardError.write("Accessibility permission not granted; titles/selection will be empty.\n".data(using: .utf8)!)
}

let workspace = NSWorkspace.shared
workspace.notificationCenter.addObserver(
    forName: NSWorkspace.didActivateApplicationNotification,
    object: nil, queue: .main
) { note in
    guard let app = note.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication else { return }
    let pid = app.processIdentifier
    let name = app.localizedName ?? ""
    emit(app: name, title: focusedWindowTitle(forPID: pid), selection: focusedSelectedText(forPID: pid))
}

// Emit the current frontmost app once at startup.
if let front = workspace.frontmostApplication {
    emit(app: front.localizedName ?? "",
         title: focusedWindowTitle(forPID: front.processIdentifier),
         selection: focusedSelectedText(forPID: front.processIdentifier))
}

RunLoop.main.run()
