import { type ReactNode } from "react";

/**
 * Lightweight inline markdown renderer.
 * Supports: [text](url), **bold**, *italic*, and newlines.
 * Links open in a new tab.
 */
export function Markdown({ text, className }: { text: string; className?: string }) {
  const lines = text.split("\n");
  return (
    <div className={className}>
      {lines.map((line, i) => (
        <p key={i} className="md-line">
          {parseLine(line)}
        </p>
      ))}
    </div>
  );
}

function parseLine(line: string): ReactNode[] {
  // Regex matches: [text](url), **bold**, *italic*
  const re = /(\[([^\]]+)\]\((https?:\/\/[^)]+)\)|\*\*(.+?)\*\*|\*(.+?)\*)/g;
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = re.exec(line)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(line.slice(lastIndex, match.index));
    }
    if (match[2] && match[3]) {
      // Link: [text](url)
      nodes.push(
        <a key={match.index} href={match[3]} target="_blank" rel="noreferrer">
          {match[2]}
        </a>
      );
    } else if (match[4]) {
      // Bold: **text**
      nodes.push(<strong key={match.index}>{match[4]}</strong>);
    } else if (match[5]) {
      // Italic: *text*
      nodes.push(<em key={match.index}>{match[5]}</em>);
    }
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < line.length) {
    nodes.push(line.slice(lastIndex));
  }
  if (nodes.length === 0) {
    nodes.push("\u00A0"); // non-breaking space for empty lines
  }

  return nodes;
}
