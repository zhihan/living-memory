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
  regenerateRotationFrom,
  createRoomInvite,
  type OccurrenceSummary,
  type SeriesSummary,
  type CheckInSummary,
  type RoomSummary,
} from "../api";
import { useAuth } from "../auth";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorMessage } from "../components/ErrorMessage";
import { formatDate } from "../dateFormat";

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

  // Inline editing state — each field is independently editable
  const [editingField, setEditingField] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [editSubmitting, setEditSubmitting] = useState(false);

  // Rotation prompt after host change
  const [showRotationPrompt, setShowRotationPrompt] = useState(false);

  // Share panel state
  const [shareOpen, setShareOpen] = useState(false);
  const [includeInvite, setIncludeInvite] = useState(false);
  const [inviteId, setInviteId] = useState<string | null>(null);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [shareCopied, setShareCopied] = useState(false);

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

  function startInlineEdit(field: string, currentValue: string) {
    setEditingField(field);
    setEditValue(currentValue);
  }

  function cancelInlineEdit() {
    setEditingField(null);
    setEditValue("");
  }

  async function saveInlineEdit(field: string, value: string) {
    if (!occurrenceId || !occurrence) return;
    setEditSubmitting(true);
    try {
      let updates: Parameters<typeof patchOccurrence>[1] = {};
      if (field === "host") {
        updates.host = value.trim() || null;
        // If host_and_location, auto-update location from host_addresses
        if (series?.rotation_mode === "host_and_location" && value.trim()) {
          const newLocation = series.host_addresses?.[value.trim()] ?? series.default_location ?? null;
          updates.location = newLocation;
        }
      } else if (field === "location") {
        updates.location = value.trim() || null;
      } else if (field === "notes") {
        updates.overrides = { ...occurrence.overrides, notes: value.trim() || null };
      } else if (field === "online_link") {
        updates.overrides = { ...occurrence.overrides, online_link: value.trim() || null };
      } else if (field === "title") {
        updates.overrides = { ...occurrence.overrides, title: value.trim() || null };
      }
      const updated = await patchOccurrence(occurrenceId, updates);
      setOccurrence(updated);
      setEditingField(null);
      setEditValue("");

      // After host change, check if we should prompt for rotation regeneration
      if (field === "host" && value.trim() && series?.host_rotation?.includes(value.trim())) {
        setShowRotationPrompt(true);
      }
    } catch (err) {
      console.error("Failed to save inline edit:", err);
      alert(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setEditSubmitting(false);
    }
  }

  async function handleRegenerateRotation() {
    if (!occurrence || !series) return;
    setEditSubmitting(true);
    try {
      await regenerateRotationFrom(series.series_id, occurrence.occurrence_id);
      setShowRotationPrompt(false);
      await load();
    } catch (err) {
      console.error("Failed to regenerate rotation:", err);
      alert(err instanceof Error ? err.message : "Failed to regenerate rotation");
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
      console.error("Failed to check in:", err);
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
      console.error("Failed to undo check-in:", err);
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
  const isOrganizer = role === "organizer";
  const isPracticeDay = occ.enable_check_in;
  const myCheckIn = checkIns.find((c) => c.user_id === user?.uid);

  const shareUrl = inviteId
    ? `${window.location.origin}/occurrences/${occurrenceId}/summary?invite=${inviteId}`
    : `${window.location.origin}/occurrences/${occurrenceId}/summary`;

  async function handleToggleInvite() {
    if (includeInvite) {
      setIncludeInvite(false);
      setInviteId(null);
      return;
    }
    setInviteLoading(true);
    try {
      const invite = await createRoomInvite(occ.room_id, "participant");
      setInviteId(invite.invite_id);
      setIncludeInvite(true);
    } catch (err) {
      console.error("Failed to create invite:", err);
      alert(err instanceof Error ? err.message : "Failed to create invite");
    } finally {
      setInviteLoading(false);
    }
  }

  async function handleCopyShareLink() {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setShareCopied(true);
      setTimeout(() => setShareCopied(false), 2000);
    } catch (err) {
      console.warn("Clipboard write failed:", err);
    }
  }

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
          {editingField === "title" ? (
            <div className="inline-edit-title">
              <input
                className="form-input page-title-input"
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") saveInlineEdit("title", editValue);
                  if (e.key === "Escape") cancelInlineEdit();
                }}
                disabled={editSubmitting}
                autoFocus
              />
              <button className="btn btn-primary btn-sm" onClick={() => saveInlineEdit("title", editValue)} disabled={editSubmitting}>Save</button>
              <button className="btn btn-secondary btn-sm" onClick={cancelInlineEdit} disabled={editSubmitting}>Cancel</button>
            </div>
          ) : (
            <h1
              className={`page-title${isManager ? " page-title-editable" : ""}`}
              style={{ margin: 0 }}
              onClick={isManager ? () => startInlineEdit("title", effectiveTitle) : undefined}
              title={isManager ? "Click to edit title" : undefined}
            >
              {effectiveTitle}
            </h1>
          )}
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => navigate(`/occurrences/${occ.next_occurrence_id}`)}
            disabled={!occ.next_occurrence_id}
            style={{ visibility: occ.next_occurrence_id ? "visible" : "hidden" }}
          >
            ›
          </button>
        </div>
        <p className="series-meta">{formatDate(occ.scheduled_for, room?.timezone, { weekday: "long", year: "numeric", month: "long", day: "numeric", hour: "numeric", minute: "2-digit" })}</p>
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
                  try {
                    const updated = await patchOccurrence(occ.occurrence_id, {
                      enable_check_in: e.target.checked,
                    });
                    setOccurrence(updated);
                  } catch (err) {
                    console.error("Failed to toggle check-in:", err);
                    alert(err instanceof Error ? err.message : "Failed to update");
                  }
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
                try {
                  await deleteOccurrence(occ.occurrence_id);
                  navigate(`/room/${occ.room_id}/series/${occ.series_id}`);
                } catch (err) {
                  console.error("Failed to delete occurrence:", err);
                  alert(err instanceof Error ? err.message : "Failed to delete occurrence");
                }
              }}
            >
              Delete occurrence
            </button>
          </div>
        </section>
      )}

      {/* Host */}
      {(occurrence?.host || (isManager && series?.host_rotation?.length)) && (
        <section className="section">
          <div className="host-banner">
            <span className="host-label">Hosted by</span>
            {editingField === "host" ? (
              <div className="inline-edit-row">
                <input
                  className="form-input"
                  list="host-rotation-options"
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") saveInlineEdit("host", editValue);
                    if (e.key === "Escape") cancelInlineEdit();
                  }}
                  placeholder="Type or select a host"
                  disabled={editSubmitting}
                  autoFocus
                />
                {series?.host_rotation?.length ? (
                  <datalist id="host-rotation-options">
                    {series.host_rotation.map((h) => (
                      <option key={h} value={h} />
                    ))}
                  </datalist>
                ) : null}
                <button className="btn btn-primary btn-sm" onClick={() => saveInlineEdit("host", editValue)} disabled={editSubmitting}>Save</button>
                <button className="btn btn-secondary btn-sm" onClick={cancelInlineEdit} disabled={editSubmitting}>Cancel</button>
              </div>
            ) : (
              <span
                className={`host-name${isManager ? " page-title-editable" : ""}`}
                onClick={isManager ? () => startInlineEdit("host", occurrence?.host ?? "") : undefined}
                title={isManager ? "Click to change host" : undefined}
              >
                {occurrence?.host || "(none)"}
              </span>
            )}
          </div>
        </section>
      )}

      {/* Rotation regeneration prompt */}
      {showRotationPrompt && (
        <section className="section">
          <div className="rotation-prompt">
            <p>Continue the rotation from this host for all following occurrences?</p>
            <div className="form-actions">
              <button className="btn btn-primary btn-sm" onClick={handleRegenerateRotation} disabled={editSubmitting}>
                {editSubmitting ? "Updating..." : "Yes, continue rotation"}
              </button>
              <button className="btn btn-secondary btn-sm" onClick={() => setShowRotationPrompt(false)} disabled={editSubmitting}>
                No, just this one
              </button>
            </div>
          </div>
        </section>
      )}

      {/* Add location prompt for "none" series with no location set */}
      {series?.location_type === "none" && !effectiveLocation && isManager && editingField !== "location" && (
        <section className="section">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => startInlineEdit("location", "")}
          >
            + Add location
          </button>
        </section>
      )}

      {/* Location & Link */}
      {(effectiveLocation || effectiveLink || (isManager && editingField === "location")) && (
        <section className="section">
          <div className="section-header">
            <h2>Location</h2>
          </div>
          <div className="location-detail">
            {editingField === "location" ? (
              <div className="inline-edit-row">
                <input
                  className="form-input"
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") saveInlineEdit("location", editValue);
                    if (e.key === "Escape") cancelInlineEdit();
                  }}
                  placeholder={series?.default_location ?? "Enter location"}
                  disabled={editSubmitting}
                  autoFocus
                />
                <button className="btn btn-primary btn-sm" onClick={() => saveInlineEdit("location", editValue)} disabled={editSubmitting}>Save</button>
                <button className="btn btn-secondary btn-sm" onClick={cancelInlineEdit} disabled={editSubmitting}>Cancel</button>
              </div>
            ) : effectiveLocation ? (
              <div
                className={`location-detail-item${isManager ? " page-title-editable" : ""}`}
                onClick={isManager ? () => startInlineEdit("location", effectiveLocation) : undefined}
                title={isManager ? "Click to edit location" : undefined}
              >
                <span className="location-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/>
                    <circle cx="12" cy="10" r="3"/>
                  </svg>
                </span>
                {effectiveLocation}
              </div>
            ) : null}
            {editingField === "online_link" ? (
              <div className="inline-edit-row">
                <input
                  className="form-input"
                  type="url"
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") saveInlineEdit("online_link", editValue);
                    if (e.key === "Escape") cancelInlineEdit();
                  }}
                  placeholder={series?.default_online_link ?? "https://..."}
                  disabled={editSubmitting}
                  autoFocus
                />
                <button className="btn btn-primary btn-sm" onClick={() => saveInlineEdit("online_link", editValue)} disabled={editSubmitting}>Save</button>
                <button className="btn btn-secondary btn-sm" onClick={cancelInlineEdit} disabled={editSubmitting}>Cancel</button>
              </div>
            ) : effectiveLink ? (
              <div
                className={`location-detail-item${isManager ? " page-title-editable" : ""}`}
                onClick={isManager ? () => startInlineEdit("online_link", effectiveLink) : undefined}
                title={isManager ? "Click to edit link" : undefined}
              >
                <span className="location-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M15 10l4.553-2.069A1 1 0 0121 8.82v6.36a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z"/>
                  </svg>
                </span>
                <a href={effectiveLink} target="_blank" rel="noreferrer" className="join-link">
                  Join online meeting
                </a>
              </div>
            ) : null}
          </div>
        </section>
      )}

      {/* Notes */}
      <section className="section">
        {editingField === "notes" ? (
          <>
            <div className="section-header"><h2>Notes</h2></div>
            <div className="inline-edit-row" style={{ flexDirection: "column", alignItems: "stretch" }}>
              <textarea
                className="form-input form-textarea"
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") cancelInlineEdit();
                }}
                rows={3}
                placeholder="Agenda, reminders, etc."
                disabled={editSubmitting}
                autoFocus
              />
              <div className="form-actions">
                <button className="btn btn-primary btn-sm" onClick={() => saveInlineEdit("notes", editValue)} disabled={editSubmitting}>Save</button>
                <button className="btn btn-secondary btn-sm" onClick={cancelInlineEdit} disabled={editSubmitting}>Cancel</button>
              </div>
            </div>
          </>
        ) : effectiveNotes ? (
          <>
            <div className="section-header"><h2>Notes</h2></div>
            <p
              className={`occurrence-notes${isManager ? " page-title-editable" : ""}`}
              onClick={isManager ? () => startInlineEdit("notes", effectiveNotes) : undefined}
              title={isManager ? "Click to edit notes" : undefined}
            >
              {effectiveNotes}
            </p>
          </>
        ) : isManager ? (
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => startInlineEdit("notes", "")}
          >
            + Add notes
          </button>
        ) : null}
      </section>



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

      {/* Share */}
      {(effectiveLocation || effectiveLink) && (
        <section className="section">
          <div className="section-header">
            <h2>Share</h2>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setShareOpen(!shareOpen)}
            >
              {shareOpen ? "Close" : "Share"}
            </button>
          </div>
          {!shareOpen && (
            <p className="placeholder-sm">
              Share meeting details with participants.
            </p>
          )}
          {shareOpen && (
            <div className="share-panel">
              <div className="share-url-row">
                <input
                  type="text"
                  className="share-url-input"
                  value={shareUrl}
                  readOnly
                  onFocus={(e) => e.target.select()}
                />
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={handleCopyShareLink}
                >
                  {shareCopied ? "Copied!" : "Copy"}
                </button>
              </div>
              {isOrganizer && (
                <label className="share-invite-toggle">
                  <input
                    type="checkbox"
                    checked={includeInvite}
                    disabled={inviteLoading}
                    onChange={handleToggleInvite}
                  />
                  <span>Include invite link (joins as participant)</span>
                </label>
              )}
              <div className="share-actions">
                <Link
                  to={`/occurrences/${occurrenceId}/summary${inviteId ? `?invite=${inviteId}` : ""}`}
                  className="btn btn-secondary btn-sm"
                  target="_blank"
                >
                  Preview
                </Link>
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
