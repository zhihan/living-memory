import type { MemoryItem } from "../api";
import { MemoryCard } from "./MemoryCard";

function parseDate(s: string): Date {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function today(): Date {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

function weekStart(t: Date): Date {
  const d = new Date(t);
  d.setDate(d.getDate() - d.getDay());
  return d;
}

function weekEnd(t: Date): Date {
  const start = weekStart(t);
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  return end;
}

function isExpired(expiresStr: string | null, t: Date): boolean {
  if (!expiresStr) return false;
  return t > parseDate(expiresStr);
}

function Section({
  title,
  memories,
  onDelete,
}: {
  title: string;
  memories: MemoryItem[];
  onDelete?: (id: string) => void;
}) {
  return (
    <section>
      <h2 className="section-heading">{title}</h2>
      {memories.length === 0 ? (
        <p className="placeholder">No events.</p>
      ) : (
        <ul className="memory-list">
          {memories.map((m) => (
            <MemoryCard key={m.id} memory={m} onDelete={onDelete} />
          ))}
        </ul>
      )}
    </section>
  );
}

export function MemoryList({
  memories,
  onDelete,
}: {
  memories: MemoryItem[];
  onDelete?: (id: string) => void;
}) {
  const t = today();
  const wStart = weekStart(t);
  const wEnd = weekEnd(t);

  const active = memories.filter((m) => !isExpired(m.expires, t));

  active.sort((a, b) => {
    const aHas = a.target != null ? 1 : 0;
    const bHas = b.target != null ? 1 : 0;
    if (aHas !== bHas) return aHas - bHas;
    if (!a.target || !b.target) return 0;
    return a.target < b.target ? -1 : a.target > b.target ? 1 : 0;
  });

  const thisWeek = active.filter(
    (m) =>
      m.target == null ||
      (parseDate(m.target) >= wStart && parseDate(m.target) <= wEnd),
  );
  const upcoming = active.filter(
    (m) => m.target != null && parseDate(m.target) > wEnd,
  );

  return (
    <>
      <Section title="This Week" memories={thisWeek} onDelete={onDelete} />
      <Section title="Upcoming" memories={upcoming} onDelete={onDelete} />
    </>
  );
}
