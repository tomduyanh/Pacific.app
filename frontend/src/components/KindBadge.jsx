export function KindBadge({ kind }) {
  const badgeClass =
    kind === "meta"
      ? "ctx-pill-meta"
      : kind === "file"
      ? "ctx-pill-file"
      : kind === "data"
      ? "ctx-pill-data"
      : "ctx-pill-people";

  return <span className={`ctx-kind-pill ${badgeClass}`}>{kind}</span>;
}

export function KindSquare({ kind }) {
  const iconClass =
    kind === "meta"
      ? "ctx-icon-meta"
      : kind === "file"
      ? "ctx-icon-file"
      : kind === "data"
      ? "ctx-icon-data"
      : "ctx-icon-people";

  const letter =
    kind === "meta"
      ? "M"
      : kind === "file"
      ? "F"
      : kind === "data"
      ? "D"
      : "P";

  return <span className={`ctx-row-icon ${iconClass}`}>{letter}</span>;
}

export function KindChipIcon({ kind }) {
  const iconClass =
    kind === "meta"
      ? "ctx-icon-meta"
      : kind === "file"
      ? "ctx-icon-file"
      : kind === "data"
      ? "ctx-icon-data"
      : "ctx-icon-people";

  const letter =
    kind === "meta"
      ? "M"
      : kind === "file"
      ? "F"
      : kind === "data"
      ? "D"
      : "P";

  return <span className={`ctx-chip-icon ${iconClass}`}>{letter}</span>;
}
