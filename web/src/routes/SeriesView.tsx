import { useEffect, useState, useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import {
  getSeries,
  getSeriesOccurrences,
  patchSeries,
  patchOccurrence,
  generateOccurrences,
  getWorkspace,
  type SeriesSummary,
  type OccurrenceSummary,
  type ScheduleRule,
  type WorkspaceSummary,
} from "../api";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorMessage } from "../components/ErrorMessage";
import { AssistantChat } from "../AssistantChat";
import { Markdown } from "../components/Markdown";

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
    rescheduled: "badge-status-confirmed",
    completed: "badge-status-completed",
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
  const [workspace, setWorkspace] = useState<WorkspaceSummary | null>(null);
  const [occurrences, setOccurrences] = useState<OccurrenceSummary[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editLocation, setEditLocation] = useState("");
  const [editLocationType, setEditLocationType] = useState<"fixed" | "per_occurrence">("fixed");
  const [editLink, setEditLink] = useState("");
  const [editTime, setEditTime] = useState("");
  const [editDuration, setEditDuration] = useState("");
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  // Next meeting agenda
  const [editingAgenda, setEditingAgenda] = useState(false);
  const [agendaText, setAgendaText] = useState("");
  const [agendaSaving, setAgendaSaving] = useState(false);

  // Assistant
  const [showAssistant, setShowAssistant] = useState(false);

  const load = useCallback(async () => {
    if (!seriesId || !workspaceId) return;
    setLoading(true);
    setError(null);
    try {
      const [s, occ, ws] = await Promise.all([
        getSeries(seriesId),
        getSeriesOccurrences(seriesId),
        getWorkspace(workspaceId),
      ]);
      setSeries(s);
      setOccurrences(occ);
      setWorkspace(ws);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [seriesId, workspaceId]);

  useEffect(() => { load(); }, [load]);

  function startEdit() {
    if (!series) return;
    setEditTitle(series.title);
    setEditDescription(series.description ?? "");
    setEditLocation(series.default_location ?? "");
    setEditLocationType(series.location_type ?? "fixed");
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
        location_type: editLocationType,
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

  async function handleSaveAgenda(occurrenceId: string) {
    setAgendaSaving(true);
    try {
      const updated = await patchOccurrence(occurrenceId, {
        overrides: { notes: agendaText.trim() || null },
      });
      setOccurrences((prev) =>
        prev?.map((o) => (o.occurrence_id === occurrenceId ? updated : o)) ?? null,
      );
      setEditingAgenda(false);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to save agenda");
    } finally {
      setAgendaSaving(false);
    }
  }

  if (loading) return <LoadingSpinner message="Loading series..." />;
  if (error) return <ErrorMessage error={error} onRetry={load} />;

  const upcoming = occurrences?.filter(
    (o) => !["completed", "cancelled"].includes(o.status),
  ) ?? [];
  const past = occurrences?.filter(
    (o) => ["completed", "cancelled"].includes(o.status),
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
        </h1>
        {series && (
          <p className="series-meta">
            {formatScheduleRule(series.schedule_rule)}
            {series.default_time && ` at ${series.default_time}`}
            {series.default_duration_minutes && ` (${series.default_duration_minutes}m)`}
          </p>
        )}
        {series?.description && (
          <Markdown text={series.description} className="series-description" />
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
            <label htmlFor="edit-desc">Description (markdown supported)</label>
            <textarea
              id="edit-desc"
              className="form-input form-textarea"
              value={editDescription}
              onChange={(e) => setEditDescription(e.target.value)}
              disabled={editSubmitting}
              placeholder={"Add resources, links, and notes.\ne.g. [Study Guide](https://example.com)"}
              rows={4}
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
            <label>Location type</label>
            <div className="visibility-toggle">
              <button
                type="button"
                className={`btn btn-sm ${editLocationType === "fixed" ? "btn-primary" : "btn-secondary"}`}
                onClick={() => setEditLocationType("fixed")}
                disabled={editSubmitting}
              >
                Fixed location
              </button>
              <button
                type="button"
                className={`btn btn-sm ${editLocationType === "per_occurrence" ? "btn-primary" : "btn-secondary"}`}
                onClick={() => setEditLocationType("per_occurrence")}
                disabled={editSubmitting}
              >
                Changes each meeting
              </button>
            </div>
          </div>
          {editLocationType === "fixed" && (
            <div className="form-field">
              <label htmlFor="edit-location">Default location</label>
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
          )}
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

      {/* Last & Next Meetings */}
      <section className="section">
        <div className="section-header">
          <h2>Meetings</h2>
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

        {past.length > 0 && (() => {
          const last = past[0];
          return (
            <div className="meeting-card meeting-card-past">
              <div className="meeting-card-label">Last</div>
              <Link to={`/occurrences/${last.occurrence_id}`} className="meeting-card-date">
                {formatDate(last.scheduled_for)}
              </Link>
              <span className={`badge ${statusColor(last.status)}`}>{last.status}</span>
              {last.overrides?.notes && (
                <p className="meeting-card-notes">{last.overrides.notes.length > 120 ? last.overrides.notes.slice(0, 120) + "…" : last.overrides.notes}</p>
              )}
            </div>
          );
        })()}

        {upcoming.length > 0 ? (() => {
          const next = upcoming[0];
          const nextNotes = next.overrides?.notes;
          return (
            <div className="meeting-card meeting-card-next">
              <div className="meeting-card-header">
                <div className="meeting-card-label">Next</div>
                {!editingAgenda && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-xs"
                    onClick={() => {
                      setAgendaText(nextNotes ?? "");
                      setEditingAgenda(true);
                    }}
                  >
                    {nextNotes ? "Edit agenda" : "Add agenda"}
                  </button>
                )}
              </div>
              <Link to={`/occurrences/${next.occurrence_id}`} className="meeting-card-date">
                {formatDate(next.scheduled_for)}
              </Link>
              {(next.location ?? next.overrides?.location) && (
                <span className="meeting-card-location">{next.location ?? next.overrides?.location}</span>
              )}
              {editingAgenda ? (
                <div className="next-meeting-edit">
                  <textarea
                    className="form-input form-textarea"
                    value={agendaText}
                    onChange={(e) => setAgendaText(e.target.value)}
                    rows={3}
                    placeholder="e.g. Chapter 5: Romans, Discussion questions..."
                    disabled={agendaSaving}
                  />
                  <div className="form-actions">
                    <button
                      type="button"
                      className="btn btn-primary btn-xs"
                      onClick={() => handleSaveAgenda(next.occurrence_id)}
                      disabled={agendaSaving}
                    >
                      {agendaSaving ? "Saving..." : "Save"}
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-xs"
                      onClick={() => setEditingAgenda(false)}
                      disabled={agendaSaving}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : nextNotes ? (
                <p className="meeting-card-notes">{nextNotes}</p>
              ) : (
                <p className="placeholder-sm">No agenda set.</p>
              )}
            </div>
          );
        })() : (
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

      {/* AI Assistant */}
      <section className="section">
        <div className="section-header">
          <h2>AI Assistant</h2>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setShowAssistant((v) => !v)}
          >
            {showAssistant ? "Hide Assistant" : "Open Assistant"}
          </button>
        </div>
        {showAssistant && workspaceId && (
          <AssistantChat
            workspaceId={workspaceId}
            context={{
              series: series ? {
                series_id: series.series_id,
                title: series.title,
                description: series.description,
                schedule_rule: series.schedule_rule,
                default_time: series.default_time,
                default_duration_minutes: series.default_duration_minutes,
                default_location: series.default_location,
                default_online_link: series.default_online_link,
              } : undefined,
              workspace: workspace ? {
                workspace_id: workspace.workspace_id,
                title: workspace.title,
                timezone: workspace.timezone,
              } : undefined,
              upcoming_count: upcoming.length,
              next_meeting: upcoming[0] ? {
                occurrence_id: upcoming[0].occurrence_id,
                scheduled_for: upcoming[0].scheduled_for,
                notes: upcoming[0].overrides?.notes,
              } : undefined,
            }}
          />
        )}
      </section>

    </div>
  );
}
