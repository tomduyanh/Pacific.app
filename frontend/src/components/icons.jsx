/**
 * Single-weight line icons for the activity stream.
 *
 * Replaces the emoji set (✉️💬🌐✏️💾📖🔍📁↗️🗑️⚡), which rendered in a
 * different illustration style and stroke weight on every platform. These
 * inherit `currentColor` and share one 1.5px stroke, so they read as a set.
 */

const BASE = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": "true",
  focusable: "false",
};

export const MailIcon = () => (
  <svg {...BASE}>
    <rect x="2.5" y="5" width="19" height="14" rx="2" />
    <path d="m3 7 8.15 5.4a1.5 1.5 0 0 0 1.7 0L21 7" />
  </svg>
);

export const ChatIcon = () => (
  <svg {...BASE}>
    <path d="M20.5 12a8 8 0 0 1-8 8H4l1.9-3.2A8 8 0 1 1 20.5 12Z" />
  </svg>
);

export const GlobeIcon = () => (
  <svg {...BASE}>
    <circle cx="12" cy="12" r="9" />
    <path d="M3.2 9h17.6M3.2 15h17.6" />
    <path d="M12 3a15 15 0 0 1 0 18a15 15 0 0 1 0-18Z" />
  </svg>
);

export const EditIcon = () => (
  <svg {...BASE}>
    <path d="M4 20h4L19 9a2.1 2.1 0 0 0-3-3L5 17v3Z" />
    <path d="m14.5 7.5 2 2" />
  </svg>
);

export const SaveIcon = () => (
  <svg {...BASE}>
    <path d="M5 3h11l3 3v15H5Z" />
    <path d="M8 3v6h7V3M8 21v-6h8v6" />
  </svg>
);

export const ReadIcon = () => (
  <svg {...BASE}>
    <path d="M12 6.5C10.5 5 8.5 4.5 4 4.5v13c4.5 0 6.5.5 8 2 1.5-1.5 3.5-2 8-2v-13c-4.5 0-6.5.5-8 2Z" />
    <path d="M12 6.5v13" />
  </svg>
);

export const SearchIcon = () => (
  <svg {...BASE}>
    <circle cx="10.5" cy="10.5" r="6.5" />
    <path d="m15.5 15.5 4.5 4.5" />
  </svg>
);

export const FolderIcon = () => (
  <svg {...BASE}>
    <path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
  </svg>
);

export const MoveIcon = () => (
  <svg {...BASE}>
    <path d="M8 16 16 8" />
    <path d="M9.5 8H16v6.5" />
  </svg>
);

export const TrashIcon = () => (
  <svg {...BASE}>
    <path d="M4 7h16" />
    <path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    <path d="M6 7v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7" />
    <path d="M10.5 11v6M13.5 11v6" />
  </svg>
);

export const PulseIcon = () => (
  <svg {...BASE}>
    <path d="M2.5 12h4l2.5-6 4 12 2.5-6h6" />
  </svg>
);

/** Map a FileGram event to its icon. Mirrors the label switch in ActivityLog. */
export function eventIcon(event) {
  switch (event.type) {
    case "browse":
      if (event.file?.includes("mail.google")) return <MailIcon />;
      if (event.file?.includes("chatgpt")) return <ChatIcon />;
      return <GlobeIcon />;
    case "edit":
      return <EditIcon />;
    case "write":
      return <SaveIcon />;
    case "read":
      return <ReadIcon />;
    case "search":
    case "grep":
    case "glob":
      return <SearchIcon />;
    case "mkdir":
      return <FolderIcon />;
    case "move":
    case "rename":
      return <MoveIcon />;
    case "delete":
      return <TrashIcon />;
    default:
      return <PulseIcon />;
  }
}
