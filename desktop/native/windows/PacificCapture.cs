// Pacific — Windows native capture helper (Subsystem A).
//
// Streams newline-delimited JSON on stdout when the foreground window changes:
//   {"app_name":"chrome","window_title":"Inbox - Gmail","selected_text":"..."}
//
// Uses UI Automation for the focused element's selected text and Win32
// GetForegroundWindow for the active app + window title. (Frames are captured on
// the Electron side via desktopCapturer; to follow the plan's Graphics Capture
// API path, add a frame stream here and forward it to live-tick.)
//
// Build (Developer Command Prompt, .NET Framework):
//   csc /target:exe /out:PacificCapture.exe PacificCapture.cs ^
//       /reference:UIAutomationClient.dll /reference:UIAutomationTypes.dll
//
// The Electron native bridge auto-detects native/windows/PacificCapture.exe.

using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Automation;

class PacificCapture
{
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);

    static string Json(string s)
    {
        if (s == null) return "";
        return s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", " ").Replace("\r", " ");
    }

    static string SelectedText()
    {
        try
        {
            var el = AutomationElement.FocusedElement;
            if (el == null) return "";
            object pattern;
            if (el.TryGetCurrentPattern(TextPattern.Pattern, out pattern))
            {
                var tp = (TextPattern)pattern;
                var ranges = tp.GetSelection();
                if (ranges != null && ranges.Length > 0)
                {
                    var sb = new StringBuilder();
                    foreach (var r in ranges) sb.Append(r.GetText(800));
                    return sb.ToString();
                }
            }
        }
        catch { /* element may not support TextPattern */ }
        return "";
    }

    static void Main()
    {
        string last = "";
        while (true)
        {
            try
            {
                IntPtr hwnd = GetForegroundWindow();
                var sb = new StringBuilder(512);
                GetWindowText(hwnd, sb, sb.Capacity);
                string title = sb.ToString();

                uint pid;
                GetWindowThreadProcessId(hwnd, out pid);
                string app = "";
                try { app = Process.GetProcessById((int)pid).ProcessName; } catch { }

                string sig = app + " " + title;
                if (sig != last)
                {
                    last = sig;
                    string sel = SelectedText();
                    Console.WriteLine("{\"app_name\":\"" + Json(app) + "\",\"window_title\":\"" +
                        Json(title) + "\",\"selected_text\":\"" + Json(sel) + "\"}");
                    Console.Out.Flush();
                }
            }
            catch { /* keep polling */ }
            Thread.Sleep(1000);
        }
    }
}
