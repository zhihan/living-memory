import { useEffect, useState, useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import {
  getSeries,
  getSeriesOccurrences,
  patchSeries,
  generateOccurrences,
  type SeriesSummary,
  type OccurrenceSummary,
  type ScheduleRule,
} from "../api";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorMessage } from "../components/ErrorMessage";

function formatDate(iso: string, timezone?: string): string {
  return new Date(iso).toLocaleString("en-US", {
    timeZone: timezone,
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatScheduleRule(rule: ScheduleRule): string {
  if (rule.frequency === "daily") return "Every day";
  if (rule.frequency === "weekdays") return "Weekdays (Mon-Fri)";
  if (rule.frequency === "weekly") {
    if (rule.weekdays && rule.weekdays.length > 0) {
      const dayMap: Record<number, string> = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"};
      return "Weekly on " + rule.weekdays.map((d) => dayMap[d] ?? String(d)).join(", ");
    }
    return "Weekly";
  }
  return rule.frequency;
}

function statusColor(status: string): string {
  const map: Record<string, string> = {
    scheduled: "badge-status-scheduled",
    confirmed: "badge-status-confirmed",
    completed: "badge-status-completed",
    skipped: "badge-status-skipped",
    cancelled: "badge-status-cancelled",
  };
  return map[status] ?? "badge-status-scheduled";
}

export function SeriesView() {
  const { workspaceId, seriesId } = useParams<{
    workspaceId: string;
    seriesId: string;
  }>();

  const [series, setSeries] = useState<SeriesSummary | null>(null);
  const [occurrences, setOccurrences] = useState<OccurrenceSummary[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editLocation, setEditLocation] = useState("");
  const [editLink, setEditLink] = useState("");
  const [editTime, setEditTime] = useState("");
  const [editDuration, setEditDuration] = useState("");
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!seriesId) return;
    setLoading(true);
    setError(null);
    try {
      const [s, occ] = await Promise.all([
        getSeries(seriesId),
        getSeriesOccurrences(seriesId),
      ]);
      setSeries(s);
      setOccurrences(occ);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [seriesId]);

  useEffect(() => { load(); }, [load]);

  function startEdit() {
    if (!series) return;
    setEditTitle(series.title);
    setEditDescription(series.description ?? "");
    setEditLocation(series.default_location ?? "");
    setEditLink(series.default_online_link ?? "");
    setEditTime(series.default_time ?? "");
    setEditDuration(series.default_duration_minutes?.toString() ?? "");
    setEditing(true);
    setEditError(null);
  }

  async function handleSaveEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!seriesId) return;
    setEditSubmitting(true);
    setEditError(null);
    try {
      const updated = await patchSeries(seriesId, {
        title: editTitle.trim() || undefined,
        description: editDescription.trim() || undefined,
        default_location: editLocation.trim() || undefined,
        default_online_link: editLink.trim() || undefined,
        default_time: editTime || undefined,
        default_duration_minutes: editDuration ? parseInt(editDuration, 10) : undefined,
      });
      setSeries(updated);
      setEditing(false);
    } catch (err) {
      setEditError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setEditSubmitting(false);
    }
  }

  async function handleGenerate() {
    if (!seriesId) return;
    setGenerating(true);
    setGenerateError(null);
    try {
      const newOcc = await generateOccurrences(seriesId, 60);
      setOccurrences(newOcc);
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : "Failed to generate");
    } finally {
      setGenerating(false);
    }
  }

  if (loading) return <LoadingSpinner message="Loading series..." />;
  if (error) return <ErrorMessage error={error} onRetry={load} />;

  const upcoming = occurrences?.filter(
    (o) => !["completed", "skipped", "cancelled"].includes(o.status),
  ) ?? [];
  const past = occurrences?.filter(
    (o) => ["completed", "skipped", "cancelled"].includes(o.status),
  ) ?? [];

  return (
    <div className="workspace-view">
      <div className="page-header">
        <div className="page-header-top">
          <Link to={`/w/${workspaceId}`} className="back-link">
            &larr; Workspace
          </Link>
          {!editing && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={startEdit}
            >
              Edit
            </button>
          )}
        </div>
        <h1 className="page-title">
          {series?.title}
          {series && (
            <span className={`badge badge-status-${series.status}`}>{series.status}</span>
          )}
        </h1>
        {series && (
          <p className="series-meta">
            {formatScheduleRule(series.schedule_rule)}
            {series.default_time && ` at ${series.default_time}`}
            {series.default_duration_minutes && ` (${series.default_duration_minutes}m)`}
          </p>
        )}
        {series?.description && (
          <p className="series-description">{series.description}</p>
        )}
        {series && (series.default_location || series.default_online_link) && (
          <div className="series-location-row">
            {series.default_location && (
              <span className="location-chip">{series.default_location}</span>
            )}
            {series.default_online_link && (
              <a
                href={series.default_online_link}
                target="_blank"
                rel="noreferrer"
                className="link-chip"
              >
                Join online
              </a>
            )}
          </div>
        )}
      </div>

      {editing && (
        <form className="create-page-form" onSubmit={handleSaveEdit}>
          <div className="form-field">
            <label htmlFor="edit-title">Title</label>
            <input
              id="edit-title"
              type="text"
              className="form-input"
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              disabled={editSubmitting}
              required
            />
          </div>
          <div className="form-field">
            <label htmlFor="edit-desc">Description</label>
            <input
              id="edit-desc"
              type="text"
              className="form-input"
              value={editDescription}
              onChange={(e) => setEditDescription(e.target.value)}
              disabled={editSubmitting}
              placeholder="Optional"
            />
          </div>
          <div className="form-row">
            <div className="form-field form-field-half">
              <label htmlFor="edit-time">Start Time</label>
              <input
                id="edit-time"
                type="time"
                className="form-input"
                value={editTime}
                onChange={(e) => setEditTime(e.target.value)}
                disabled={editSubmitting}
              />
            </div>
            <div className="form-field form-field-half">
              <label htmlFor="edit-duration">Duration (min)</label>
              <input
                id="edit-duration"
                type="number"
                className="form-input"
                value={editDuration}
                onChange={(e) => setEditDuration(e.target.value)}
                min="5"
                max="480"
                disabled={editSubmitting}
              />
            </div>
          </div>
          <div className="form-field">
            <label htmlFor="edit-location">Location</label>
            <input
              id="edit-location"
              type="text"
              className="form-input"
              value={editLocation}
              onChange={(e) => setEditLocation(e.target.value)}
              disabled={editSubmitting}
              placeholder="Room or address"
            />
          </div>
          <div className="form-field">
            <label htmlFor="edit-link">Online Link</label>
            <input
              id="edit-link"
              type="url"
              className="form-input"
              value={editLink}
              onChange={(e) => setEditLink(e.target.value)}
              disabled={editSubmitting}
              placeholder="https://zoom.us/j/..."
            />
          </div>
          {editError && <p className="form-error">{editError}</p>}
          <div className="form-actions">
            <button
              type="submit"
              className="btn btn-primary btn-sm"
              disabled={editSubmitting}
            >
              {editSubmitting ? "Saving..." : "Save Changes"}
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => { setEditing(false); setEditError(null); }}
              disabled={editSubmitting}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      <section className="section">
        <div className="section-header">
          <h2>Upcoming</h2>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={handleGenerate}
            disabled={generating}
          >
            {generating ? "Generating..." : "Refresh schedule"}
          </button>
        </div>
        {generateError && <p className="form-error">{generateError}</p>}
        {upcoming.length > 0 ? (
          <ul className="occurrence-list">
            {upcoming.slice(0, 10).map((occ) => (
              <OccurrenceRow
                key={occ.occurrence_id}
                occ={occ}
              />
            ))}
          </ul>
        ) : (
          <p className="placeholder">
            No upcoming occurrences.{" "}
            <button
              type="button"
              className="btn-link"
              onClick={handleGenerate}
              disabled={generating}
            >
              Generate schedule
            </button>
          </p>
        )}
      </section>

      {past.length > 0 && (
        <section className="section">
          <div className="section-header">
            <h2>Past</h2>
          </div>
          <ul className="occurrence-list occurrence-list-past">
            {past.slice(0, 5).map((occ) => (
              <OccurrenceRow
                key={occ.occurrence_id}
                occ={occ}
              />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function OccurrenceRow({
  occ,
}: {
  occ: OccurrenceSummary;
}) {
  const title = occ.overrides.title ?? null;
  const location = occ.overrides.location;
  const link = occ.overrides.online_link;

  return (
    <li className="occurrence-card">
      <Link to={`/occurrences/${occ.occurrence_id}`} className="occurrence-card-date">
        {formatDate(occ.scheduled_for)}
      </Link>
      {title && <span className="occurrence-override-label">{title}</span>}
      <span className={`badge ${statusColor(occ.status)}`}>{occ.status}</span>
      {(location || link) && (
        <div className="occurrence-location">
          {location && <span className="location-chip">{location}</span>}
          {link && (
            <a href={link} target="_blank" rel="noreferrer" className="link-chip">
              Join
            </a>
          )}
        </div>
      )}
    </li>
  );
}
