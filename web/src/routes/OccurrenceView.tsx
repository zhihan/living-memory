import { useEffect, useState, useCallback } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import {
  getOccurrence,
  getSeries,
  getRoom,
  patchOccurrence,
  createCheckIn,
  getOccurrenceCheckIns,
  getMyOccurrenceCheckIn,
  deleteCheckIn,
  deleteOccurrence,
  type OccurrenceSummary,
  type SeriesSummary,
  type OccurrenceOverrides,
  type CheckInSummary,
  type RoomSummary,
} from "../api";
import { useAuth } from "../auth";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorMessage } from "../components/ErrorMessage";


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
  const navigate = useNavigate();

  const { user } = useAuth();

  const [occurrence, setOccurrence] = useState<OccurrenceSummary | null>(null);
  const [series, setSeries] = useState<SeriesSummary | null>(null);
  const [room, setRoom] = useState<RoomSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  // Check-ins
  const [checkIns, setCheckIns] = useState<CheckInSummary[]>([]);
  const [checkInSubmitting, setCheckInSubmitting] = useState(false);

  // Edit overrides
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editLocation, setEditLocation] = useState("");
  const [editLink, setEditLink] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [editDuration, setEditDuration] = useState("");
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);



  const load = useCallback(async () => {
    if (!occurrenceId) return;
    setLoading(true);
    setError(null);
    try {
      const occ = await getOccurrence(occurrenceId);
      const [s, ws] = await Promise.all([
        getSeries(occ.series_id),
        getRoom(occ.room_id),
      ]);
      const role = user?.uid ? ws.member_roles[user.uid] : undefined;
      const isManager = role === "organizer" || role === "teacher";
      let cis: CheckInSummary[];
      if (isManager) {
        cis = await getOccurrenceCheckIns(occurrenceId);
      } else {
        const myCheckIn = await getMyOccurrenceCheckIn(occurrenceId);
        cis = myCheckIn ? [myCheckIn] : [];
      }
      setOccurrence(occ);
      setSeries(s);
      setRoom(ws);
      setCheckIns(cis);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [occurrenceId, user?.uid]);

  useEffect(() => { load(); }, [load]);

  // Keyboard shortcuts for prev/next navigation
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "ArrowLeft" && occurrence?.prev_occurrence_id) navigate(`/occurrences/${occurrence.prev_occurrence_id}`);
      if (e.key === "ArrowRight" && occurrence?.next_occurrence_id) navigate(`/occurrences/${occurrence.next_occurrence_id}`);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [occurrence?.prev_occurrence_id, occurrence?.next_occurrence_id, navigate]);

  function startEdit() {
    if (!occurrence) return;
    setEditTitle(occurrence.overrides?.title ?? "");
    setEditLocation(occurrence.location ?? occurrence.overrides?.location ?? "");
    setEditLink(occurrence.overrides?.online_link ?? "");
    setEditNotes(occurrence.overrides?.notes ?? "");
    setEditDuration(occurrence.overrides?.duration_minutes?.toString() ?? "");
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
    if (editLink.trim()) overrides.online_link = editLink.trim();
    if (editNotes.trim()) overrides.notes = editNotes.trim();
    if (editDuration) overrides.duration_minutes = parseInt(editDuration, 10);
    try {
      const updated = await patchOccurrence(occurrenceId, {
        location: editLocation.trim() || null,
        overrides,
      });
      setOccurrence(updated);
      setEditing(false);
    } catch (err) {
      setEditError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setEditSubmitting(false);
    }
  }

  async function handleCheckIn() {
    if (!occurrenceId) return;
    setCheckInSubmitting(true);
    try {
      const ci = await createCheckIn(occurrenceId, "confirmed");
      setCheckIns((prev) => {
        const filtered = prev.filter((c) => c.user_id !== ci.user_id);
        return [...filtered, ci];
      });
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setCheckInSubmitting(false);
    }
  }

  async function handleUndoCheckIn(checkInId: string) {
    try {
      await deleteCheckIn(checkInId);
      setCheckIns((prev) => prev.filter((c) => c.check_in_id !== checkInId));
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to undo");
    }
  }

  if (loading) return <LoadingSpinner message="Loading occurrence..." />;
  if (error) return <ErrorMessage error={error} onRetry={load} />;

  const occ = occurrence!;
  const effectiveTitle = occ.overrides?.title ?? series?.title ?? "Meeting";
  const effectiveLocation = occ.location ?? occ.overrides?.location ?? (series?.location_type !== "none" ? series?.default_location : undefined);
  const effectiveLink = occ.overrides?.online_link ?? series?.default_online_link;
  const effectiveNotes = occ.overrides?.notes;
  const effectiveDuration = occ.overrides?.duration_minutes ?? series?.default_duration_minutes;
  const role = user?.uid ? room?.member_roles[user.uid] : undefined;
  const isManager = role === "organizer" || role === "teacher";
  const isPracticeDay = occ.enable_check_in;
  const myCheckIn = checkIns.find((c) => c.user_id === user?.uid);


  return (
    <div className="room-view">
      <div className="page-header">
        <div className="page-header-top">
          <Link
            to={`/room/${occurrence?.room_id}/series/${occurrence?.series_id}`}
            className="back-link"
          >
            &larr; Series
          </Link>
          {!editing && isManager && (
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
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "1rem" }}>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => navigate(`/occurrences/${occ.prev_occurrence_id}`)}
            disabled={!occ.prev_occurrence_id}
            style={{ visibility: occ.prev_occurrence_id ? "visible" : "hidden" }}
          >
            ‹
          </button>
          <h1 className="page-title" style={{ margin: 0 }}>{effectiveTitle}</h1>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => navigate(`/occurrences/${occ.next_occurrence_id}`)}
            disabled={!occ.next_occurrence_id}
            style={{ visibility: occ.next_occurrence_id ? "visible" : "hidden" }}
          >
            ›
          </button>
        </div>
        <p className="series-meta">{formatDate(occ.scheduled_for)}</p>
        {effectiveDuration && (
          <p className="series-meta">{effectiveDuration} minutes</p>
        )}
        <p className="series-meta series-meta-link">
          <Link to={`/room/${occurrence?.room_id}/series/${occurrence?.series_id}`} className="muted-link">
            {series?.title}
          </Link>
        </p>
      </div>

      {/* Status & Actions (manager only) */}
      {isManager && (
        <section className="section">
          {/* status buttons hidden – issue #114 */}
          {series?.enable_done && (
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={occ.enable_check_in}
                onChange={async (e) => {
                  const updated = await patchOccurrence(occ.occurrence_id, {
                    enable_check_in: e.target.checked,
                  });
                  setOccurrence(updated);
                }}
              />
              <span>Show "Done" button</span>
            </label>
          )}
          <div style={{ marginTop: 8 }}>
            <button
              className="btn btn-sm btn-danger"
              onClick={async () => {
                if (!confirm("Delete this occurrence? This cannot be undone.")) return;
                await deleteOccurrence(occ.occurrence_id);
                navigate(`/room/${occ.room_id}/series/${occ.series_id}`);
              }}
            >
              Delete occurrence
            </button>
          </div>
        </section>
      )}

      {/* Host */}
      {occurrence?.host && (
        <section className="section">
          <div className="host-banner">
            <span className="host-label">Hosted by</span>
            <span className="host-name">{occurrence.host}</span>
          </div>
        </section>
      )}

      {/* Add location prompt for "none" series with no location set */}
      {series?.location_type === "none" && !effectiveLocation && !editing && isManager && (
        <section className="section">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={startEdit}
          >
            + Add location
          </button>
        </section>
      )}

      {/* Location & Link */}
      {(effectiveLocation || effectiveLink) && (
        <section className="section">
          <div className="section-header">
            <h2>Location</h2>
            {series?.location_type === "rotation" && (
              <Link
                to={`/room/${occurrence?.room_id}/series/${occurrence?.series_id}`}
                className="btn btn-secondary btn-xs"
              >
                Edit rotation
              </Link>
            )}
          </div>
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
              <label htmlFor="eo-location">Location</label>
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



      {/* Check-in section — shown on practice/study days (no location and no online link) */}
      {isPracticeDay && (
        <section className="section">
          {myCheckIn?.status === "confirmed" ? (
            <div className="checkin-done">
              <span className="checkin-done-label">Done ✓</span>
              <button
                type="button"
                className="btn btn-secondary btn-xs"
                onClick={() => handleUndoCheckIn(myCheckIn.check_in_id)}
              >
                Undo
              </button>
            </div>
          ) : (
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleCheckIn}
              disabled={checkInSubmitting}
            >
              {checkInSubmitting ? "Saving..." : "Done"}
            </button>
          )}
        </section>
      )}

      {/* Organizer: check-in report */}
      {isManager && checkIns.length > 0 && (
        <section className="section">
          <div className="section-header">
            <h2>Completions ({checkIns.length})</h2>
          </div>
          <ul className="checkin-list">
            {checkIns.map((ci) => (
              <li key={ci.check_in_id} className="checkin-item">
                <span className="checkin-name">
                  {ci.display_name ?? ci.user_id.slice(0, 8)}
                </span>
                {/* check-in status badge hidden – issue #114 */}
                {ci.checked_in_at && (
                  <span className="checkin-time">
                    {new Date(ci.checked_in_at).toLocaleTimeString("en-US", {
                      hour: "numeric",
                      minute: "2-digit",
                    })}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Shareable participant summary */}
      {(effectiveLocation || effectiveLink) && (
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
      )}
    </div>
  );
}
