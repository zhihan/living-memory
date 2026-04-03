import { useState } from "react";
import type { ResourceLink } from "../api";

interface ResourceLinksProps {
  links: ResourceLink[] | null;
  canEdit: boolean;
  onSave: (links: ResourceLink[]) => Promise<void>;
}

export function ResourceLinks({ links, canEdit, onSave }: ResourceLinksProps) {
  const [editing, setEditing] = useState(false);
  const [editLinks, setEditLinks] = useState<ResourceLink[]>([]);
  const [saving, setSaving] = useState(false);

  function startEdit() {
    setEditLinks(links?.length ? links.map((l) => ({ ...l })) : [{ label: "", url: "" }]);
    setEditing(true);
  }

  async function handleSave() {
    setSaving(true);
    try {
      const cleaned = editLinks.filter((l) => l.label.trim() && l.url.trim());
      await onSave(cleaned);
      setEditing(false);
    } catch (err) {
      console.error("Failed to save links:", err);
      alert(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  const hasLinks = links && links.length > 0;

  if (!hasLinks && !canEdit) return null;

  return (
    <section className="section">
      <div className="section-header">
        <h2>Resources</h2>
        {canEdit && !editing && (
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={startEdit}
          >
            {hasLinks ? "Edit" : "+ Add"}
          </button>
        )}
      </div>

      {editing ? (
        <div className="resource-links-edit">
          {editLinks.map((link, i) => (
            <div key={i} className="resource-link-row">
              <input
                type="text"
                className="form-input"
                value={link.label}
                onChange={(e) => {
                  const next = [...editLinks];
                  next[i] = { ...next[i], label: e.target.value };
                  setEditLinks(next);
                }}
                placeholder="Label (e.g. Study Guide)"
                disabled={saving}
              />
              <input
                type="url"
                className="form-input"
                value={link.url}
                onChange={(e) => {
                  const next = [...editLinks];
                  next[i] = { ...next[i], url: e.target.value };
                  setEditLinks(next);
                }}
                placeholder="https://..."
                disabled={saving}
              />
              <button
                type="button"
                className="btn btn-secondary btn-xs"
                onClick={() => setEditLinks(editLinks.filter((_, j) => j !== i))}
                disabled={saving}
              >
                &times;
              </button>
            </div>
          ))}
          <button
            type="button"
            className="btn btn-secondary btn-xs"
            onClick={() => setEditLinks([...editLinks, { label: "", url: "" }])}
            disabled={saving}
          >
            + Add link
          </button>
          <div className="form-actions">
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? "Saving..." : "Save"}
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setEditing(false)}
              disabled={saving}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : hasLinks ? (
        <ul className="resource-links-list">
          {links.map((link, i) => (
            <li key={i} className="resource-link-item">
              <a href={link.url} target="_blank" rel="noreferrer">
                {link.label}
              </a>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
