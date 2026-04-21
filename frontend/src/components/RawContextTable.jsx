import { useState } from "react";
import { KindBadge, KindSquare } from "./KindBadge.jsx";

const TABS = ["All", "Meta-context", "Files", "Data", "People"];
const KIND_MAP = {
  "Meta-context": "meta",
  Files: "file",
  Data: "data",
  People: "people",
};

function formatSize(bytes) {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatRelativeTime(isoString) {
  if (!isoString) return "—";
  const now = Date.now();
  const ts = new Date(isoString).getTime();
  const diffMs = now - ts;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffSec < 90) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHour < 6) return `${diffHour}h ago`;
  if (diffDay === 0) return "today";
  if (diffDay === 1) return "yesterday";
  if (diffDay < 7) return new Date(isoString).toLocaleDateString("en-US", { weekday: "short" });
  return `${Math.floor(diffDay / 7)}w ago`;
}

export function RawContextTable({ pool, onAttach, onDetach, onItemClick }) {
  const [activeTab, setActiveTab] = useState("All");
  const [search, setSearch] = useState("");

  const counts = {
    "Meta-context": pool.filter((i) => i.kind === "meta").length,
    Files: pool.filter((i) => i.kind === "file").length,
    Data: pool.filter((i) => i.kind === "data").length,
    People: pool.filter((i) => i.kind === "people").length,
  };

  const filtered = pool
    .filter((item) => {
      if (activeTab !== "All" && item.kind !== KIND_MAP[activeTab]) return false;
      if (search) {
        const q = search.toLowerCase();
        return item.display_name.toLowerCase().includes(q) || item.description.toLowerCase().includes(q);
      }
      return true;
    })
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0));

  return (
    <div className="ctx-section">
      <div className="ctx-section-head">
        <h3 className="ctx-section-title">Raw context</h3>
        <div className="ctx-section-meta">{pool.length} entries total</div>
      </div>

      <div className="ctx-tabs">
        {TABS.map((tab) => {
          const count = tab === "All" ? pool.length : counts[tab] ?? 0;
          return (
            <div
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`ctx-tab ${activeTab === tab ? "active" : ""}`}
            >
              {tab}
              <span className="ctx-tab-count">{count}</span>
            </div>
          );
        })}
        <div className="ctx-tab-spacer"></div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search..."
          className="ctx-tab-search"
        />
      </div>

      <div className="ctx-rowhead">
        <span></span>
        <span>Name</span>
        <span>Kind</span>
        <span>Size</span>
        <span>Last used</span>
        <span>Status</span>
      </div>

      <div>
        {filtered.map((item) => (
          <TableRow key={item.id} item={item} onAttach={onAttach} onDetach={onDetach} onItemClick={onItemClick} />
        ))}
      </div>

      {filtered.length === 0 && (
        <div style={{ padding: '32px 0', textAlign: 'center', fontSize: '13px', color: 'var(--color-text-tertiary)' }}>
          No context blocks match your filter.
        </div>
      )}
    </div>
  );
}

function TableRow({ item, onAttach, onDetach, onItemClick }) {
  const isActive = item.status === "active";
  const isSuggested = item.status === "suggested";

  return (
    <div className="ctx-row" title={item.source} onClick={() => onItemClick?.(item)} style={{ cursor: 'pointer' }}>
      <KindSquare kind={item.kind} />
      <div className="ctx-row-name-col">
        <div className="ctx-row-name" title={item.display_name}>{item.display_name}</div>
        <div className="ctx-row-sub" title={item.description}>{item.description}</div>
      </div>
      <span>
        <KindBadge kind={item.kind} />
      </span>
      <span className="ctx-row-meta">{formatSize(item.size_bytes)}</span>
      <span className="ctx-row-meta">{formatRelativeTime(item.last_used)}</span>
      <span>
        {isActive ? (
          <span className="ctx-state-on" onClick={(e) => { e.stopPropagation(); onDetach(item.id); }}>active</span>
        ) : isSuggested ? (
          <span className="ctx-state-suggested" onClick={(e) => { e.stopPropagation(); onAttach(item.id); }}>recommended</span>
        ) : (
          <span className="ctx-state-off" onClick={(e) => { e.stopPropagation(); onAttach(item.id); }}>idle</span>
        )}
      </span>
    </div>
  );
}
