import { useEffect, useState, useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import {
  getOccurrence,
  getSeries,
  getOccurrenceCheckIns,
  patchOccurrence,
  createCheckIn,
  type OccurrenceSummary,
  type SeriesSummary,
  type CheckInSummary,
  type OccurrenceOverrides,
} from "../api";
import { useAuth } from "../auth";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorMessage } from "../components/ErrorMessage";

const OCCURRENCE_STATUSES = ["scheduled", "confirmed", "completed", "skipped", "cancelled"];

function formatDate(iso: string, timezone?: string): string {
  return new Date(iso).toLocaleString("en-US", {
    timeZone: timezone,
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function OccurrenceView() {
  const { occurrenceId } = useParams<{ occurrenceId: string }>();
  const { user } = useAuth();

  const [occurrence, setOccurrence] = useState<OccurrenceSummary | null>(null);
  const [series, setSeries] = useState<SeriesSummary | null>(null);
  const [checkIns, setCheckIns] = useState<CheckInSummary[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  // Edit overrides
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editLocation, setEditLocation] = useState("");
  const [editLink, setEditLink] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [editDuration, setEditDuration] = useState("");
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Status change
  const [statusChanging, setStatusChanging] = useState(false);

  // Check-in
  const [checkingIn, setCheckingIn] = useState(false);

  const load = useCallback(async () => {
    if (!occurrenceId) return;
    setLoading(true);
    setError(null);
    try {
      const occ = await getOccurrence(occurrenceId);
      const [s, ci] = await Promise.all([
        getSeries(occ.series_id),
        getOccurrenceCheckIns(occurrenceId),
      ]);
      setOccurrence(occ);
      setSeries(s);
      setCheckIns(ci);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [occurrenceId]);

  useEffect(() => { load(); }, [load]);

  function startEdit() {
    if (!occurrence) return;
    setEditTitle(occurrence.overrides.title ?? "");
    setEditLocation(occurrence.overrides.location ?? "");
    setEditLink(occurrence.overrides.online_link ?? "");
    setEditNotes(occurrence.overrides.notes ?? "");
    setEditDuration(occurrence.overrides.duration_minutes?.toString() ?? "");
    setEditing(true);
    setEditError(null);
  }

  async function handleSaveEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!occurrenceId) return;
    setEditSubmitting(true);
    setEditError(null);
    const overrides: OccurrenceOverrides = {};
    if (editTitle.trim()) overrides.title = editTitle.trim();
    if (editLocation.trim()) overrides.location = editLocation.trim();
    if (editLink.trim()) overrides.online_link = editLink.trim();
    if (editNotes.trim()) overrides.notes = editNotes.trim();
    if (editDuration) overrides.duration_minutes = parseInt(editDuration, 10);
    try {
      const updated = await patchOccurrence(occurrenceId, { overrides });
      setOccurrence(updated);
      setEditing(false);
    } catch (err) {
      setEditError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setEditSubmitting(false);
    }
  }

  async function handleStatusChange(newStatus: string) {
    if (!occurrenceId) return;
    setStatusChanging(true);
    try {
      const updated = await patchOccurrence(occurrenceId, { status: newStatus });
      setOccurrence(updated);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to update status");
    } finally {
      setStatusChanging(false);
    }
  }

  async function handleCheckIn() {
    if (!occurrenceId) return;
    setCheckingIn(true);
    try {
      const ci = await createCheckIn(occurrenceId, "present");
      setCheckIns((prev) => [...(prev ?? []), ci]);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to check in");
    } finally {
      setCheckingIn(false);
    }
  }

  if (loading) return <LoadingSpinner message="Loading occurrence..." />;
  if (error) return <ErrorMessage error={error} onRetry={load} />;

  const occ = occurrence!;
  const effectiveTitle = occ.overrides.title ?? series?.title ?? "Meeting";
  const effectiveLocation = occ.overrides.location ?? series?.default_location;
  const effectiveLink = occ.overrides.online_link ?? series?.default_online_link;
  const effectiveNotes = occ.overrides.notes;
  const effectiveDuration = occ.overrides.duration_minutes ?? series?.default_duration_minutes;

  const alreadyCheckedIn = checkIns?.some((ci) => ci.user_id === user?.uid);

  return (
    <div className="workspace-view">
      <div className="page-header">
        <div className="page-header-top">
          <Link
            to={`/w/${occurrence?.workspace_id}/series/${occurrence?.series_id}`}
            className="back-link"
          >
            &larr; Series
          </Link>
          {!editing && (
            <div className="header-actions">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={startEdit}
              >
                Edit this occurrence
              </button>
            </div>
          )}
        </div>
        <h1 className="page-title">{effectiveTitle}</h1>
        <p className="series-meta">{formatDate(occ.scheduled_for)}</p>
        {effectiveDuration && (
          <p className="series-meta">{effectiveDuration} minutes</p>
        )}
        <p className="series-meta series-meta-link">
          <Link to={`/w/${occurrence?.workspace_id}/series/${occurrence?.series_id}`} className="muted-link">
            {series?.title}
          </Link>
        </p>
      </div>

      {/* Status & Actions */}
      <section className="section">
        <div className="section-header">
          <h2>Status</h2>
        </div>
        <div className="status-row">
          {OCCURRENCE_STATUSES.map((s) => (
            <button
              key={s}
              type="button"
              className={`btn btn-sm ${occ.status === s ? "btn-primary" : "btn-secondary"}`}
              onClick={() => occ.status !== s && handleStatusChange(s)}
              disabled={statusChanging || occ.status === s}
            >
              {s}
            </button>
          ))}
        </div>
      </section>

      {/* Location & Link */}
      {(effectiveLocation || effectiveLink) && (
        <section className="section">
          <div className="section-header"><h2>Location</h2></div>
          <div className="location-detail">
            {effectiveLocation && (
              <div className="location-detail-item">
                <span className="location-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/>
                    <circle cx="12" cy="10" r="3"/>
                  </svg>
                </span>
                {effectiveLocation}
              </div>
            )}
            {effectiveLink && (
              <div className="location-detail-item">
                <span className="location-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M15 10l4.553-2.069A1 1 0 0121 8.82v6.36a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z"/>
                  </svg>
                </span>
                <a href={effectiveLink} target="_blank" rel="noreferrer" className="join-link">
                  Join online meeting
                </a>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Notes */}
      {effectiveNotes && (
        <section className="section">
          <div className="section-header"><h2>Notes</h2></div>
          <p className="occurrence-notes">{effectiveNotes}</p>
        </section>
      )}

      {/* Edit form for this occurrence only */}
      {editing && (
        <section className="section">
          <div className="section-header">
            <h2>Edit This Occurrence</h2>
            <span className="edit-scope-note">Changes apply to this meeting only</span>
          </div>
          <form className="create-page-form" onSubmit={handleSaveEdit}>
            <div className="form-field">
              <label htmlFor="eo-title">Title override</label>
              <input
                id="eo-title"
                type="text"
                className="form-input"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                placeholder={series?.title ?? ""}
                disabled={editSubmitting}
              />
            </div>
            <div className="form-field">
              <label htmlFor="eo-duration">Duration (min)</label>
              <input
                id="eo-duration"
                type="number"
                className="form-input"
                value={editDuration}
                onChange={(e) => setEditDuration(e.target.value)}
                min="5"
                max="480"
                disabled={editSubmitting}
              />
            </div>
            <div className="form-field">
              <label htmlFor="eo-location">Location override</label>
              <input
                id="eo-location"
                type="text"
                className="form-input"
                value={editLocation}
                onChange={(e) => setEditLocation(e.target.value)}
                placeholder={series?.default_location ?? ""}
                disabled={editSubmitting}
              />
            </div>
            <div className="form-field">
              <label htmlFor="eo-link">Online link override</label>
              <input
                id="eo-link"
                type="url"
                className="form-input"
                value={editLink}
                onChange={(e) => setEditLink(e.target.value)}
                placeholder={series?.default_online_link ?? ""}
                disabled={editSubmitting}
              />
            </div>
            <div className="form-field">
              <label htmlFor="eo-notes">Notes</label>
              <textarea
                id="eo-notes"
                className="form-input form-textarea"
                value={editNotes}
                onChange={(e) => setEditNotes(e.target.value)}
                rows={3}
                placeholder="Agenda, reminders, etc."
                disabled={editSubmitting}
              />
            </div>
            {editError && <p className="form-error">{editError}</p>}
            <div className="form-actions">
              <button
                type="submit"
                className="btn btn-primary btn-sm"
                disabled={editSubmitting}
              >
                {editSubmitting ? "Saving..." : "Save"}
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
        </section>
      )}

      {/* Check-ins */}
      <section className="section">
        <div className="section-header">
          <h2>Check-ins ({checkIns?.length ?? 0})</h2>
          {!alreadyCheckedIn && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={handleCheckIn}
              disabled={checkingIn}
            >
              {checkingIn ? "Checking in..." : "Check in"}
            </button>
          )}
        </div>
        {checkIns && checkIns.length > 0 ? (
          <ul className="checkin-list">
            {checkIns.map((ci) => (
              <li key={ci.check_in_id} className="checkin-item">
                <span className={`badge badge-ci-${ci.status}`}>{ci.status}</span>
                <span className="checkin-uid">{ci.user_id.slice(0, 8)}…</span>
                {ci.checked_in_at && (
                  <span className="checkin-time">
                    {new Date(ci.checked_in_at).toLocaleTimeString([], {
                      hour: "numeric",
                      minute: "2-digit",
                    })}
                  </span>
                )}
                {ci.note && <span className="checkin-note">{ci.note}</span>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="placeholder">No check-ins yet.</p>
        )}
      </section>

      {/* Shareable participant summary */}
      <section className="section">
        <div className="section-header">
          <h2>Participant Summary</h2>
          <Link
            to={`/occurrences/${occurrenceId}/summary`}
            className="btn btn-secondary btn-sm"
          >
            View shareable page
          </Link>
        </div>
        <p className="placeholder-sm">
          Share the summary link with participants for Zoom and location details.
        </p>
      </section>
    </div>
  );
}
