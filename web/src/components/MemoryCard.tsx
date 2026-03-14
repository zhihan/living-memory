import type { MemoryItem } from "../api";

function formatDate(dateStr: string): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  return date.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function renderInlineMarkdown(text: string): string {
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  // markdown links [text](url)
  html = html.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>',
  );
  // bare URLs
  html = html.replace(
    /(?<!href="|">)(https?:\/\/\S+?)(?=[)<\s]|$)/g,
    '<a href="$1" target="_blank" rel="noopener">$1</a>',
  );
  return html;
}

function attachmentLabel(url: string): string {
  try {
    const path = decodeURIComponent(new URL(url).pathname);
    return path.split("/").pop() || "attachment";
  } catch {
    return "attachment";
  }
}

const IconCalendar = () => (
  <svg viewBox="0 0 24 24">
    <rect x="3" y="4" width="18" height="18" rx="2" />
    <line x1="16" y1="2" x2="16" y2="6" />
    <line x1="8" y1="2" x2="8" y2="6" />
    <line x1="3" y1="10" x2="21" y2="10" />
  </svg>
);

const IconOngoing = () => (
  <svg viewBox="0 0 24 24">
    <path d="M12 2L2 7l10 5 10-5-10-5z" />
    <path d="M2 17l10 5 10-5" />
    <path d="M2 12l10 5 10-5" />
  </svg>
);

const IconChevron = () => (
  <svg className="chevron" viewBox="0 0 24 24">
    <polyline points="9 18 15 12 9 6" />
  </svg>
);

export function MemoryCard({
  memory,
  onDelete,
}: {
  memory: MemoryItem;
  onDelete?: (id: string) => void;
}) {
  const title = memory.title || memory.content;
  const meta: string[] = [];
  if (memory.target) meta.push(formatDate(memory.target));
  if (memory.time) meta.push(memory.time);
  if (memory.place) meta.push(memory.place);

  const hasDetails =
    meta.length > 0 ||
    (memory.title && memory.content) ||
    (memory.attachments && memory.attachments.length > 0);

  const icon = memory.target ? <IconCalendar /> : <IconOngoing />;

  return (
    <li className="memory-card">
      <details>
        <summary>
          <div className="summary-icon">{icon}</div>
          <div className="summary-body">
            <div className="summary-title-row">
              <div
                className="summary-title"
                dangerouslySetInnerHTML={{ __html: renderInlineMarkdown(title) }}
              />
              {memory.visibility === "members" && (
                <span className="badge badge-members">members only</span>
              )}
            </div>
            {meta.length > 0 && (
              <div className="summary-meta">{meta.join(" \u00b7 ")}</div>
            )}
          </div>
          {hasDetails && <IconChevron />}
          {onDelete && (
            <button
              className="memory-delete-btn"
              title="Delete memory"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                if (confirm(`Delete "${title}"?`)) onDelete(memory.id);
              }}
            >
              ×
            </button>
          )}
        </summary>
        {hasDetails && (
          <div className="detail-body">
            {meta.length > 0 && <p>{meta.join("\n")}</p>}
            {memory.title && memory.content && (
              <div
                dangerouslySetInnerHTML={{
                  __html: renderInlineMarkdown(memory.content),
                }}
              />
            )}
            {memory.attachments && memory.attachments.length > 0 && (
              <div className="attachments">
                {memory.attachments.map((url) => (
                  <a
                    key={url}
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    &#128206; {attachmentLabel(url)}
                  </a>
                ))}
              </div>
            )}
          </div>
        )}
      </details>
    </li>
  );
}
