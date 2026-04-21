export function ActivityLog({ events }) {
  const getEventIcon = (event) => {
    switch (event.type) {
      case "browse":
        if (event.file?.includes("mail.google")) return "✉️";
        if (event.file?.includes("chatgpt"))     return "💬";
        return "🌐";
      case "edit":   return "✏️";
      case "write":  return "💾";
      case "read":   return "📖";
      case "search":
      case "grep":
      case "glob":   return "🔍";
      case "mkdir":  return "📁";
      case "move":
      case "rename": return "↗️";
      case "delete": return "🗑️";
      default:       return "⚡";
    }
  };

  const getEventLabel = (event) => {
    const prefix =
      event.source === "vlm_screen_live" ? "Live · " :
      event.source === "vlm_screen"      ? "VLM · "  : "";
    switch (event.type) {
      case "browse":
        if (event.file?.includes("mail.google")) return `${prefix}Reading Email: Product Launch`;
        if (event.file?.includes("chatgpt"))     return `${prefix}Chatting on ChatGPT`;
        return `${prefix}Browsing: ${event.file || "Unknown page"}`;
      case "edit":
        return `${prefix}Edited: ${event.file || "Unknown"} (+${event.lines_added || 0} / -${event.lines_removed || 0})`;
      case "read":
        return `${prefix}Read: ${event.file}`;
      case "write":
        return `${prefix}Wrote: ${event.file || "Unknown"}`;
      case "search":
      case "grep":
      case "glob":
        return `${prefix}${event.type}: ${event.file || ""}`;
      case "mkdir":
        return `${prefix}Created dir: ${event.dir || event.file || ""}`;
      case "move":
      case "rename":
        return `${prefix}${event.type}: ${event.file || "(no path)"}`;
      case "delete":
        return `${prefix}Deleted: ${event.file || "(no path)"}`;
      default:
        return `${prefix}${event.type} event`;
    }
  };

  const getSourceBadge = (event) => {
    if (event.source === "vlm_screen_live") return { label: "Live", cls: "al-badge al-badge-live" };
    if (event.source === "vlm_screen")      return { label: "VLM",  cls: "al-badge al-badge-vlm"  };
    return null;
  };

  const formatTime = (ts) => {
    if (!ts) return null;
    const d = new Date(typeof ts === "number" ? ts * 1000 : ts);
    if (isNaN(d.getTime())) return null;
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };

  const recentEvents = [...(events || [])].reverse().slice(0, 50);

  return (
    <div className="activity-log-container">
      <div className="activity-log-header">
        <div className="al-header-left">
          <h3 className="activity-log-title">Activity Stream</h3>
          <span className="ctx-live-dot" title="Live connection active" />
        </div>
        <span className="al-count">{recentEvents.length} events</span>
      </div>

      <div className="activity-log-feed">
        {recentEvents.length === 0 ? (
          <div className="al-empty">
            <div className="al-empty-icon">⚡</div>
            <div className="al-empty-title">No activity yet</div>
            <div className="al-empty-sub">Events will appear here as they are captured</div>
          </div>
        ) : (
          recentEvents.map((evt, idx) => {
            const badge = getSourceBadge(evt);
            const time  = formatTime(evt.timestamp || evt.ts || evt.created_at);
            return (
              <div key={idx} className="activity-log-item">
                <div className="activity-log-icon">
                  {getEventIcon(evt)}
                </div>
                <div className="activity-log-content">
                  <div className="al-item-top">
                    <span className="activity-log-text">{getEventLabel(evt)}</span>
                    {badge && <span className={badge.cls}>{badge.label}</span>}
                  </div>
                  {time && <div className="al-item-time">{time}</div>}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
