import { useEffect, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { getPage, patchPage, type PageSummary } from "../api";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorMessage } from "../components/ErrorMessage";
import { TimezoneSelect } from "../components/TimezoneSelect";

export function PageSettings() {
  const { slug } = useParams<{ slug: string }>();
  const [page, setPage] = useState<PageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const [timezone, setTimezone] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<{ ok: boolean; text: string } | null>(
    null,
  );

  const load = useCallback(async () => {
    if (!slug) return;
    setLoading(true);
    setError(null);
    try {
      const p = await getPage(slug);
      setPage(p);
      setTimezone(p.timezone || "UTC");
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleSave() {
    if (!slug) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const updated = await patchPage(slug, { timezone });
      setPage(updated);
      setSaveMsg({ ok: true, text: "Timezone updated." });
    } catch (err) {
      setSaveMsg({
        ok: false,
        text: err instanceof Error ? err.message : "Failed to save",
      });
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <LoadingSpinner message="Loading settings..." />;
  if (error) return <ErrorMessage error={error} onRetry={load} />;

  const dirty = timezone !== (page?.timezone || "UTC");

  return (
    <div className="page-settings">
      <div className="page-header">
        <Link to={`/p/${slug}`} className="back-link">
          &larr; Back to page
        </Link>
        <h1>
          Settings
          <span className="settings-page-title">{page?.title}</span>
        </h1>
      </div>

      <section className="settings-section">
        <h2>Timezone</h2>
        <p className="settings-hint">
          Dates and times on this page are displayed in this timezone.
        </p>
        <div className="settings-row">
          <TimezoneSelect value={timezone} onChange={setTimezone} />
          <button
            className="btn btn-primary btn-sm"
            onClick={handleSave}
            disabled={saving || !dirty}
          >
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
        {saveMsg && (
          <p className={saveMsg.ok ? "settings-ok" : "form-error"}>
            {saveMsg.text}
          </p>
        )}
      </section>
    </div>
  );
}
