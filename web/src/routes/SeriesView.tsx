import { useEffect, useState, useCallback } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import {
  getSeries,
  getSeriesOccurrences,
  getSeriesCheckInReport,
  getRoom,
  patchSeries,
  deleteSeries,
  patchOccurrence,
  generateOccurrences,
  createOccurrence,
  regenerateRotationFrom,
  type RoomSummary,
  type SeriesSummary,
  type OccurrenceSummary,
  type CheckInReport,
  type ScheduleRule,
} from "../api";
import { useAuth } from "../auth";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorMessage } from "../components/ErrorMessage";
import { Markdown } from "../components/Markdown";
import { ResourceLinks } from "../components/ResourceLinks";
import { Toast } from "../components/Toast";
import { formatDate, formatShortDate } from "../dateFormat";

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

const FREQ_OPTIONS = [
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "weekdays", label: "Weekdays (Mon-Fri)" },
];

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DAY_VALUES = [1, 2, 3, 4, 5, 6, 7];


export function SeriesView() {
  const { roomId, seriesId } = useParams<{
    roomId: string;
    seriesId: string;
  }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [room, setRoom] = useState<RoomSummary | null>(null);
  const [series, setSeries] = useState<SeriesSummary | null>(null);
  const [occurrences, setOccurrences] = useState<OccurrenceSummary[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const [editing, setEditing] = useState(false);
  const [editEnableDone, setEditEnableDone] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editLocation, setEditLocation] = useState("");
  const [editLocationType, setEditLocationType] = useState<"none" | "fixed" | "per_occurrence" | "rotation">("fixed");
  const [editLink, setEditLink] = useState("");
  const [editTime, setEditTime] = useState("");
  const [editDuration, setEditDuration] = useState("");
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [editFreq, setEditFreq] = useState("weekly");
  const [editDays, setEditDays] = useState<number[]>([1]);
  const [editCheckInDays, setEditCheckInDays] = useState<number[]>([]);
  const [scheduleConfirmMode, setScheduleConfirmMode] = useState<null | "pending">(null);

  const [editExtendDate, setEditExtendDate] = useState("");
  const [editingLocationId, setEditingLocationId] = useState<string | null>(null);
  const [editingLocationValue, setEditingLocationValue] = useState("");
  const [generating, setGenerating] = useState(false);

  // Host rotation state
  const [editRotationMode, setEditRotationMode] = useState<"none" | "manual" | "host_only" | "host_and_location">("none");
  const [editHostRotation, setEditHostRotation] = useState<string[]>([]);
  const [editHostAddresses, setEditHostAddresses] = useState<Record<string, string>>({});
  const [editingHostId, setEditingHostId] = useState<string | null>(null);
  const [editingHostValue, setEditingHostValue] = useState("");
  const [toast, setToast] = useState<{ message: string; action?: { label: string; onClick: () => void } } | null>(null);

  // Next meeting agenda
  const [editingAgenda, setEditingAgenda] = useState(false);
  const [agendaText, setAgendaText] = useState("");
  const [agendaSaving, setAgendaSaving] = useState(false);

  // Add occurrence
  const [showAddOccurrence, setShowAddOccurrence] = useState(false);
  const [addOccDate, setAddOccDate] = useState("");
  const [addOccTime, setAddOccTime] = useState("");
  const [addOccSubmitting, setAddOccSubmitting] = useState(false);

  // Check-in report
  const [showReport, setShowReport] = useState(false);
  const [report, setReport] = useState<CheckInReport | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportWindow, setReportWindow] = useState(10); // number of occurrences to show


  const load = useCallback(async () => {
    if (!seriesId || !roomId) return;
    setLoading(true);
    setError(null);
    try {
      const [s, occ, rm] = await Promise.all([
        getSeries(seriesId),
        getSeriesOccurrences(seriesId),
        getRoom(roomId),
      ]);
      setSeries(s);
      setOccurrences(occ);
      setRoom(rm);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [seriesId, roomId]);

  async function loadReport() {
    if (!seriesId) return;
    setReportLoading(true);
    try {
      const r = await getSeriesCheckInReport(seriesId);
      setReport(r);
      setShowReport(true);
    } catch (err) {
      console.error("Failed to load check-in report:", err);
      alert(err instanceof Error ? err.message : "Failed to load report");
    } finally {
      setReportLoading(false);
    }
  }

  useEffect(() => { load(); }, [load]);

  const isOrganizer = user?.uid && room?.member_roles[user.uid] === "organizer";
  const occurrencePath = (id: string) => `/occurrences/${id}`;

  // Furthest scheduled occurrence date
  const lastOccurrence = occurrences?.length
    ? occurrences.reduce((a, b) => (a.scheduled_for > b.scheduled_for ? a : b))
    : null;
  const scheduledThrough = lastOccurrence
    ? formatShortDate(lastOccurrence.scheduled_for, room?.timezone)
    : null;

  function startEdit() {
    if (!series) return;
    setEditEnableDone(series.enable_done ?? false);
    setEditTitle(series.title);
    setEditDescription(series.description ?? "");
    setEditLocation(series.default_location ?? "");
    setEditLocationType(series.location_type ?? "fixed");
    setEditLink(series.default_online_link ?? "");
    setEditTime(series.default_time ?? "");
    setEditDuration(series.default_duration_minutes?.toString() ?? "");
    setEditExtendDate("");
    setEditRotationMode(series.rotation_mode ?? "none");
    setEditHostRotation(series.host_rotation ?? []);
    setEditHostAddresses(series.host_addresses ?? {});
    setEditFreq(series.schedule_rule?.frequency ?? "weekly");
    setEditDays((series.schedule_rule?.weekdays ?? [1]).map(Number).filter((n) => n >= 1 && n <= 7));
    setEditCheckInDays(series.check_in_weekdays ?? []);
    setScheduleConfirmMode(null);
    setEditing(true);
    setEditError(null);
  }

  function toggleEditDay(d: number) {
    setEditDays((prev) => prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d].sort());
  }
  function toggleEditCheckInDay(d: number) {
    setEditCheckInDays((prev) => prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d].sort());
  }

  function hasScheduleChanged(): boolean {
    if (!series) return false;
    const origFreq = series.schedule_rule?.frequency ?? "weekly";
    const origDays = series.schedule_rule?.weekdays ?? [1];
    if (editFreq !== origFreq) return true;
    if (editFreq === "weekly") {
      const sortedOrig = [...origDays].sort();
      const sortedEdit = [...editDays].sort();
      if (sortedOrig.length !== sortedEdit.length) return true;
      if (sortedOrig.some((d, i) => d !== sortedEdit[i])) return true;
    }
    return false;
  }

  async function handleSaveEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!seriesId) return;

    // Validation
    if (editRotationMode !== "none" && editRotationMode !== "manual") {
      const validHosts = editHostRotation.filter((h) => h.trim());
      if (validHosts.length === 0) {
        setEditError("Rotation requires at least one host entry");
        return;
      }
      // Check all host labels are non-empty
      if (editHostRotation.some((h) => !h.trim())) {
        setEditError("All host labels must be non-empty");
        return;
      }
    }

    if (hasScheduleChanged() && scheduleConfirmMode === null) {
      setScheduleConfirmMode("pending");
      return;
    }

    await doSave();
  }

  async function doSave(mode?: "adjust" | "regenerate") {
    if (!seriesId) return;

    setEditSubmitting(true);
    setEditError(null);
    try {
      let scheduleRule: ScheduleRule | undefined;
      if (hasScheduleChanged()) {
        if (editFreq === "weekly") {
          scheduleRule = { frequency: "weekly", weekdays: editDays.length > 0 ? editDays : [1] };
        } else {
          scheduleRule = { frequency: editFreq };
        }
      }

      const updates: Parameters<typeof patchSeries>[1] = {
        enable_done: editEnableDone,
        title: editTitle.trim() || undefined,
        description: editDescription.trim() || undefined,
        default_location: editLocation.trim() || undefined,
        default_online_link: editLink.trim() || undefined,
        location_type: editLocationType,
        default_time: editTime || undefined,
        default_duration_minutes: editDuration ? parseInt(editDuration, 10) : undefined,
        rotation_mode: editRotationMode,
        host_rotation: editRotationMode !== "none" && editRotationMode !== "manual" ? editHostRotation.filter((h) => h.trim()) : undefined,
        host_addresses: editRotationMode === "host_and_location"
          ? Object.fromEntries(Object.entries(editHostAddresses).filter(([k]) => k.trim()))
          : undefined,
        check_in_weekdays: editCheckInDays.length > 0 ? editCheckInDays : undefined,
        ...(scheduleRule ? { schedule_rule: scheduleRule, schedule_mode: mode } : {}),
      };
      console.log("PATCH series payload:", JSON.stringify(updates, null, 2));
      const updated = await patchSeries(seriesId, updates);
      setSeries(updated);
      if (editExtendDate) {
        const newOcc = await generateOccurrences(seriesId, editExtendDate);
        setOccurrences(newOcc);
      } else if (scheduleRule) {
        // Refresh occurrences after schedule change
        const newOcc = await getSeriesOccurrences(seriesId);
        setOccurrences(newOcc);
      }
      setScheduleConfirmMode(null);
      setEditing(false);
    } catch (err) {
      console.error("Failed to save series:", err);
      setEditError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setEditSubmitting(false);
    }
  }

  async function handleGenerate() {
    if (!seriesId) return;
    setGenerating(true);
    try {
      const end = new Date();
      end.setDate(end.getDate() + 60);
      const newOcc = await generateOccurrences(seriesId, end.toISOString().slice(0, 10));
      setOccurrences(newOcc);
    } catch (err) {
      console.error("Failed to generate occurrences:", err);
      alert(err instanceof Error ? err.message : "Failed to generate");
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
      console.error("Failed to save agenda:", err);
      alert(err instanceof Error ? err.message : "Failed to save agenda");
    } finally {
      setAgendaSaving(false);
    }
  }

  async function handleAddOccurrence(e: React.FormEvent) {
    e.preventDefault();
    if (!seriesId || !addOccDate) return;
    setAddOccSubmitting(true);
    try {
      const time = addOccTime || series?.default_time || "00:00";
      const tz = room?.timezone || "UTC";
      // Convert room-local date+time to UTC
      const localStr = `${addOccDate}T${time}:00`;
      const localDt = new Date(localStr);
      const utcFromLocal = new Date(localDt.toLocaleString("en-US", { timeZone: "UTC" }));
      const tzFromLocal = new Date(localDt.toLocaleString("en-US", { timeZone: tz }));
      const offsetMs = utcFromLocal.getTime() - tzFromLocal.getTime();
      const scheduledFor = new Date(localDt.getTime() + offsetMs).toISOString();
      await createOccurrence(seriesId, scheduledFor);
      const refreshed = await getSeriesOccurrences(seriesId);
      setOccurrences(refreshed);
      setShowAddOccurrence(false);
      setAddOccDate("");
      setAddOccTime("");
    } catch (err) {
      console.error("Failed to create occurrence:", err);
      alert(err instanceof Error ? err.message : "Failed to create occurrence");
    } finally {
      setAddOccSubmitting(false);
    }
  }

  if (loading) return <LoadingSpinner message="Loading series..." />;
  if (error) return <ErrorMessage error={error} onRetry={load} />;

  const now = new Date().toISOString();
  const upcoming = occurrences?.filter(
    (o) => o.scheduled_for > now && !["completed", "cancelled"].includes(o.status),
  ) ?? [];
  const past = occurrences?.filter(
    (o) => o.scheduled_for <= now || ["completed", "cancelled"].includes(o.status),
  ) ?? [];

  return (
    <div className="room-view">
      <div className="page-header">
        <div className="page-header-top">
          <Link to={`/room/${roomId}`} className="back-link">
            &larr; Room
          </Link>
          {isOrganizer && !editing && (
            <div style={{ display: "flex", gap: 4 }}>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={startEdit}
              >
                Edit
              </button>
              <button
                className="btn btn-sm btn-danger"
                onClick={async () => {
                  if (!confirm("Delete this series and all its occurrences? This cannot be undone.")) return;
                  try {
                    await deleteSeries(seriesId!);
                    navigate(`/room/${roomId}`);
                  } catch (err) {
                    console.error("Failed to delete series:", err);
                    alert(err instanceof Error ? err.message : "Failed to delete series");
                  }
                }}
              >
                Delete
              </button>
            </div>
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
            {scheduledThrough && <> · Through {scheduledThrough}</>}
          </p>
        )}
        {series?.description && (
          <Markdown text={series.description} className="series-description" />
        )}
        {series && series.location_type !== "none" && (series.default_location || series.default_online_link || (series.location_type === "rotation" && series.location_rotation?.length)) && (
          <div className="series-location-row">
            {series.location_type === "rotation" && series.location_rotation?.length ? (
              <span className="location-chip">Rotation: {series.location_rotation.join(" → ")}</span>
            ) : series.default_location ? (
              <span className="location-chip">{series.default_location}</span>
            ) : null}
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
          <div className="form-field">
            <label>Frequency</label>
            <div className="visibility-toggle">
              {FREQ_OPTIONS.map((f) => (
                <button
                  key={f.value}
                  type="button"
                  className={`btn btn-sm ${editFreq === f.value ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => setEditFreq(f.value)}
                  disabled={editSubmitting}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
          {editFreq === "weekly" && (
            <div className="form-field">
              <label>Days of Week</label>
              <div className="days-toggle">
                {DAYS.map((day, i) => (
                  <button
                    key={day}
                    type="button"
                    className={`btn btn-day ${editDays.includes(DAY_VALUES[i]) ? "btn-primary" : "btn-secondary"}`}
                    onClick={() => toggleEditDay(DAY_VALUES[i])}
                    disabled={editSubmitting}
                  >
                    {day}
                  </button>
                ))}
              </div>
            </div>
          )}
          {/* "Done" button + day filter moved below rotation fields */}
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
          {editRotationMode !== "host_and_location" && (
            <div className="form-field">
              <label>Location type</label>
              <div className="visibility-toggle">
                <button
                  type="button"
                  className={`btn btn-sm ${editLocationType === "none" ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => setEditLocationType("none")}
                  disabled={editSubmitting}
                >
                  None
                </button>
                <button
                  type="button"
                  className={`btn btn-sm ${editLocationType === "fixed" ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => setEditLocationType("fixed")}
                  disabled={editSubmitting}
                >
                  Fixed
                </button>
                <button
                  type="button"
                  className={`btn btn-sm ${editLocationType === "per_occurrence" ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => setEditLocationType("per_occurrence")}
                  disabled={editSubmitting}
                >
                  Per meeting
                </button>
              </div>
            </div>
          )}
          {editRotationMode === "host_and_location" && (
            <div className="form-field">
              <span className="form-hint">Locations are set per host below.</span>
            </div>
          )}
          {editLocationType === "fixed" && editRotationMode !== "host_and_location" && (
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
          <div className="form-field">
            <label>Host Rotation</label>
            <div className="visibility-toggle">
              <button
                type="button"
                className={`btn btn-sm ${editRotationMode === "none" ? "btn-primary" : "btn-secondary"}`}
                onClick={() => setEditRotationMode("none")}
                disabled={editSubmitting}
              >
                No host
              </button>
              <button
                type="button"
                className={`btn btn-sm ${editRotationMode === "manual" ? "btn-primary" : "btn-secondary"}`}
                onClick={() => setEditRotationMode("manual")}
                disabled={editSubmitting}
              >
                Manual
              </button>
              <button
                type="button"
                className={`btn btn-sm ${editRotationMode === "host_only" ? "btn-primary" : "btn-secondary"}`}
                onClick={() => setEditRotationMode("host_only")}
                disabled={editSubmitting}
              >
                Rotating hosts
              </button>
              {editLocationType !== "none" && (
                <button
                  type="button"
                  className={`btn btn-sm ${editRotationMode === "host_and_location" ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => setEditRotationMode("host_and_location")}
                  disabled={editSubmitting}
                >
                  Rotate host + location
                </button>
              )}
            </div>
          </div>
          {editRotationMode !== "none" && editRotationMode !== "manual" && (
            <div className="form-field">
              <label>Host rotation order</label>
              {editHostRotation.map((hostLabel, i) => (
                <div key={i} className="rotation-row">
                  <span className="rotation-index">{i + 1}.</span>
                  <input
                    type="text"
                    className="form-input"
                    value={hostLabel}
                    onChange={(e) => {
                      const oldName = editHostRotation[i];
                      const next = [...editHostRotation];
                      next[i] = e.target.value;
                      setEditHostRotation(next);
                      if (editRotationMode === "host_and_location" && oldName !== e.target.value) {
                        const newAddresses = { ...editHostAddresses };
                        if (oldName in newAddresses) {
                          newAddresses[e.target.value] = newAddresses[oldName];
                          delete newAddresses[oldName];
                        }
                        setEditHostAddresses(newAddresses);
                      }
                    }}
                    disabled={editSubmitting}
                    placeholder="e.g. Team A, Alice, Bob's family"
                  />
                  {editRotationMode === "host_and_location" && (
                    <input
                      type="text"
                      className="form-input"
                      value={editHostAddresses[hostLabel] || ""}
                      onChange={(e) => {
                        setEditHostAddresses({
                          ...editHostAddresses,
                          [hostLabel]: e.target.value,
                        });
                      }}
                      disabled={editSubmitting}
                      placeholder="Location address"
                    />
                  )}
                  <button
                    type="button"
                    className="btn btn-secondary btn-xs"
                    onClick={() => {
                      setEditHostRotation(editHostRotation.filter((_, j) => j !== i));
                      if (editRotationMode === "host_and_location") {
                        const next = { ...editHostAddresses };
                        delete next[hostLabel];
                        setEditHostAddresses(next);
                      }
                    }}
                    disabled={editSubmitting}
                  >
                    &times;
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-xs"
                    onClick={() => {
                      if (i > 0) {
                        const next = [...editHostRotation];
                        [next[i - 1], next[i]] = [next[i], next[i - 1]];
                        setEditHostRotation(next);
                      }
                    }}
                    disabled={editSubmitting || i === 0}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-xs"
                    onClick={() => {
                      if (i < editHostRotation.length - 1) {
                        const next = [...editHostRotation];
                        [next[i], next[i + 1]] = [next[i + 1], next[i]];
                        setEditHostRotation(next);
                      }
                    }}
                    disabled={editSubmitting || i === editHostRotation.length - 1}
                  >
                    ↓
                  </button>
                </div>
              ))}
              <button
                type="button"
                className="btn btn-secondary btn-xs"
                onClick={() => setEditHostRotation([...editHostRotation, ""])}
                disabled={editSubmitting}
              >
                + Add host
              </button>
            </div>
          )}
          <div className="form-field">
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={editEnableDone}
                onChange={(e) => {
                  setEditEnableDone(e.target.checked);
                  if (!e.target.checked) setEditCheckInDays([]);
                }}
                disabled={editSubmitting}
              />
              <span>Show "Done" button</span>
            </label>
            {editEnableDone && editDays.length > 0 && (
              <div style={{ marginTop: "0.5rem" }}>
                <label style={{ fontSize: "0.9rem", color: "#666", marginBottom: "0.25rem", display: "block" }}>on:</label>
                <div className="days-toggle">
                  {DAYS.map((day, i) => {
                    const dv = DAY_VALUES[i];
                    if (!editDays.includes(dv)) return null;
                    return (
                      <button
                        key={day}
                        type="button"
                        className={`btn btn-day ${editCheckInDays.includes(dv) ? "btn-primary" : "btn-secondary"}`}
                        onClick={() => toggleEditCheckInDay(dv)}
                        disabled={editSubmitting}
                      >
                        {day}
                      </button>
                    );
                  })}
                </div>
                <span className="form-hint">
                  {editCheckInDays.length === 0
                    ? "All occurrences — or edit individual occurrences to choose"
                    : "Only occurrences on selected days"}
                </span>
              </div>
            )}
          </div>
          <div className="form-field">
            <label htmlFor="edit-extend">Extend schedule to</label>
            <input
              id="edit-extend"
              type="date"
              className="form-input"
              value={editExtendDate}
              onChange={(e) => setEditExtendDate(e.target.value)}
              disabled={editSubmitting}
              min={new Date().toISOString().slice(0, 10)}
            />
            {scheduledThrough && !editExtendDate && (
              <span className="form-hint">Currently scheduled through {scheduledThrough}</span>
            )}
          </div>
          {editError && <p className="form-error">{editError}</p>}
          {scheduleConfirmMode === "pending" && (
            <div className="form-field" style={{ background: "#fff8e1", padding: "1rem", borderRadius: "8px", border: "1px solid #ffe082" }}>
              <p style={{ margin: "0 0 0.5rem", fontWeight: 600 }}>Schedule changed. How should existing occurrences be updated?</p>
              <p style={{ margin: "0 0 1rem", fontSize: "0.9rem", color: "#666" }}>
                Completed and modified occurrences are always preserved.
              </p>
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <button type="button" className="btn btn-primary" onClick={() => doSave("adjust")} disabled={editSubmitting}>
                  Adjust schedule
                </button>
                <button type="button" className="btn btn-secondary" style={{ color: "#c62828" }} onClick={() => doSave("regenerate")} disabled={editSubmitting}>
                  Delete future &amp; regenerate
                </button>
                <button type="button" className="btn btn-secondary" onClick={() => setScheduleConfirmMode(null)} disabled={editSubmitting}>
                  Cancel
                </button>
              </div>
            </div>
          )}
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
          {isOrganizer && !showAddOccurrence && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => {
                setAddOccTime(series?.default_time ?? "");
                setShowAddOccurrence(true);
              }}
            >
              + Add occurrence
            </button>
          )}
        </div>
        {showAddOccurrence && (
          <form className="add-occurrence-form" onSubmit={handleAddOccurrence}>
            <div className="inline-edit-row" style={{ flexWrap: "wrap" }}>
              <input
                type="date"
                className="form-input"
                value={addOccDate}
                onChange={(e) => setAddOccDate(e.target.value)}
                required
                disabled={addOccSubmitting}
                style={{ flex: "1 1 140px" }}
              />
              <input
                type="time"
                className="form-input"
                value={addOccTime}
                onChange={(e) => setAddOccTime(e.target.value)}
                disabled={addOccSubmitting}
                style={{ flex: "0 0 110px" }}
              />
              <button type="submit" className="btn btn-primary btn-sm" disabled={addOccSubmitting || !addOccDate}>
                {addOccSubmitting ? "Adding..." : "Add"}
              </button>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowAddOccurrence(false)} disabled={addOccSubmitting}>
                Cancel
              </button>
            </div>
          </form>
        )}

        {past.length > 0 && (() => {
          const last = past[past.length - 1];
          return (
            <div className="meeting-card meeting-card-past">
              <div className="meeting-card-label">Last</div>
              <Link to={occurrencePath(last.occurrence_id)} className="meeting-card-date">
                {formatDate(last.scheduled_for, room?.timezone)}
              </Link>
              {/* status badge hidden – issue #114 */}
              {last.overrides?.notes && (
                <p className="meeting-card-notes">{last.overrides.notes.length > 120 ? last.overrides.notes.slice(0, 120) + "…" : last.overrides.notes}</p>
              )}
            </div>
          );
        })()}

        {past.length > 1 && (
          <div className="upcoming-list">
            <h3 className="upcoming-list-heading">Past</h3>
            {past.slice().reverse().slice(1, 7).map((o) => (
              <div key={o.occurrence_id} className="upcoming-row">
                <Link to={occurrencePath(o.occurrence_id)} className="upcoming-date">
                  {formatDate(o.scheduled_for, room?.timezone)}
                </Link>
                {o.overrides?.notes && (
                  <span className="meeting-card-notes" style={{ fontSize: "0.85rem", color: "#666" }}>
                    {o.overrides.notes.length > 60 ? o.overrides.notes.slice(0, 60) + "…" : o.overrides.notes}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}

        {upcoming.length > 0 ? (() => {
          const next = upcoming[0];
          const nextNotes = next.overrides?.notes;
          return (
            <div className="meeting-card meeting-card-next">
              <div className="meeting-card-header">
                <div className="meeting-card-label">Next</div>
              </div>
              <Link to={occurrencePath(next.occurrence_id)} className="meeting-card-date">
                {formatDate(next.scheduled_for, room?.timezone)}
              </Link>
              {(series?.location_type !== "none" || next.location) && (
                isOrganizer && editingLocationId === next.occurrence_id ? (
                  <input
                    type="text"
                    className="form-input form-input-sm upcoming-location-input"
                    value={editingLocationValue}
                    onChange={(e) => setEditingLocationValue(e.target.value)}
                    autoFocus
                    placeholder="Location"
                    onBlur={async () => {
                      const newLoc = editingLocationValue.trim();
                      if (newLoc === (next.location ?? "")) {
                        setEditingLocationId(null);
                        return;
                      }
                      try {
                        const updated = await patchOccurrence(next.occurrence_id, {
                          location: newLoc || null,
                        });
                        setOccurrences((prev) =>
                          prev?.map((x) => (x.occurrence_id === next.occurrence_id ? updated : x)) ?? null,
                        );
                      } catch (err) {
                        console.error("Failed to save occurrence:", err);
                        alert(err instanceof Error ? err.message : "Failed to save");
                      }
                      setEditingLocationId(null);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                      if (e.key === "Escape") setEditingLocationId(null);
                    }}
                  />
                ) : (
                  <span
                    className={`meeting-card-location${isOrganizer ? " upcoming-location-clickable" : ""}`}
                    onClick={isOrganizer ? () => {
                      setEditingLocationId(next.occurrence_id);
                      setEditingLocationValue(next.location ?? "");
                    } : undefined}
                    tabIndex={isOrganizer ? 0 : undefined}
                    role={isOrganizer ? "button" : undefined}
                    title={isOrganizer ? "Click to edit" : undefined}
                  >
                    {next.location || (isOrganizer ? "Set location" : "")}
                  </span>
                )
              )}
              {series?.rotation_mode && series.rotation_mode !== "none" && (
                isOrganizer && editingHostId === next.occurrence_id ? (
                  <input
                    type="text"
                    className="form-input form-input-sm upcoming-host-input"
                    value={editingHostValue}
                    onChange={(e) => setEditingHostValue(e.target.value)}
                    autoFocus
                    placeholder="Host"
                    onBlur={async () => {
                      const newHost = editingHostValue.trim();
                      if (newHost === (next.host ?? "")) {
                        setEditingHostId(null);
                        return;
                      }
                      try {
                        const patchPayload: Parameters<typeof patchOccurrence>[1] = {
                          host: newHost || null,
                        };
                        const hostAddress =
                          series?.rotation_mode === "host_and_location" && newHost
                            ? series.host_addresses?.[newHost]
                            : undefined;
                        if (hostAddress) {
                          patchPayload.location = hostAddress;
                        }
                        const updated = await patchOccurrence(next.occurrence_id, patchPayload);
                        setOccurrences((prev) =>
                          prev?.map((x) => (x.occurrence_id === next.occurrence_id ? updated : x)) ?? null,
                        );
                        if (newHost && series?.host_rotation?.includes(newHost)) {
                          const toastMsg = hostAddress
                            ? `Host updated to "${newHost}" · Location: ${hostAddress}`
                            : `Host updated to "${newHost}"`;
                          setToast({
                            message: toastMsg,
                            action: {
                              label: "Continue rotation from here →",
                              onClick: async () => {
                                try {
                                  const result = await regenerateRotationFrom(seriesId!, next.occurrence_id);
                                  await load();
                                  setToast({
                                    message: `Updated ${result.updated_count} upcoming occurrences`,
                                  });
                                } catch (err) {
                                  console.error("Failed to regenerate rotation:", err);
                                  alert(err instanceof Error ? err.message : "Failed to regenerate rotation");
                                }
                              },
                            },
                          });
                        }
                      } catch (err) {
                        console.error("Failed to save occurrence:", err);
                        alert(err instanceof Error ? err.message : "Failed to save");
                      }
                      setEditingHostId(null);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                      if (e.key === "Escape") setEditingHostId(null);
                    }}
                  />
                ) : (
                  <span
                    className={`upcoming-host${isOrganizer ? " upcoming-host-clickable" : ""}`}
                    onClick={isOrganizer ? () => {
                      setEditingHostId(next.occurrence_id);
                      setEditingHostValue(next.host ?? "");
                    } : undefined}
                    tabIndex={isOrganizer ? 0 : undefined}
                    role={isOrganizer ? "button" : undefined}
                    title={isOrganizer ? "Click to edit host" : undefined}
                  >
                    {next.host ? `Host: ${next.host}` : (isOrganizer ? "Set host" : "")}
                  </span>
                )
              )}
              {isOrganizer && editingAgenda ? (
                <div className="next-meeting-edit">
                  <textarea
                    className="form-input form-textarea"
                    value={agendaText}
                    onChange={(e) => setAgendaText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Escape") setEditingAgenda(false);
                    }}
                    rows={3}
                    placeholder="e.g. Chapter 5: Romans, Discussion questions..."
                    disabled={agendaSaving}
                    autoFocus
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
                <p
                  className={`meeting-card-notes${isOrganizer ? " page-title-editable" : ""}`}
                  onClick={isOrganizer ? () => {
                    setAgendaText(nextNotes);
                    setEditingAgenda(true);
                  } : undefined}
                  title={isOrganizer ? "Click to edit" : undefined}
                >
                  {nextNotes}
                </p>
              ) : isOrganizer ? (
                <p
                  className="placeholder-sm page-title-editable"
                  onClick={() => {
                    setAgendaText("");
                    setEditingAgenda(true);
                  }}
                  title="Click to add notes"
                >
                  + Add notes
                </p>
              ) : null}
            </div>
          );
        })() : (
          <p className="placeholder">
            No upcoming occurrences.{isOrganizer && (<>{" "}
            <button
              type="button"
              className="btn-link"
              onClick={handleGenerate}
              disabled={generating}
            >
              Generate schedule
            </button></>)}
          </p>
        )}

        {upcoming.length > 1 && (
          <div className="upcoming-list">
            <h3 className="upcoming-list-heading">Upcoming</h3>
            {upcoming.slice(1, 7).map((o) => (
              <div key={o.occurrence_id} className="upcoming-row">
                <Link to={occurrencePath(o.occurrence_id)} className="upcoming-date">
                  {formatDate(o.scheduled_for, room?.timezone)}
                </Link>
                {(series?.location_type !== "none" || o.location) && (
                  isOrganizer && editingLocationId === o.occurrence_id ? (
                    <input
                      type="text"
                      className="form-input form-input-sm upcoming-location-input"
                      value={editingLocationValue}
                      onChange={(e) => setEditingLocationValue(e.target.value)}
                      autoFocus
                      placeholder="Location"
                      onBlur={async () => {
                        const newLoc = editingLocationValue.trim();
                        if (newLoc === (o.location ?? "")) {
                          setEditingLocationId(null);
                          return;
                        }
                        try {
                          const updated = await patchOccurrence(o.occurrence_id, {
                            location: newLoc || null,
                          });
                          setOccurrences((prev) =>
                            prev?.map((x) => (x.occurrence_id === o.occurrence_id ? updated : x)) ?? null,
                          );
                        } catch (err) {
                          alert(err instanceof Error ? err.message : "Failed to save");
                        }
                        setEditingLocationId(null);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                        if (e.key === "Escape") setEditingLocationId(null);
                      }}
                    />
                  ) : (
                    <span
                      className={`upcoming-location${isOrganizer ? " upcoming-location-clickable" : ""}`}
                      onClick={isOrganizer ? () => {
                        setEditingLocationId(o.occurrence_id);
                        setEditingLocationValue(o.location ?? "");
                      } : undefined}
                      tabIndex={isOrganizer ? 0 : undefined}
                      role={isOrganizer ? "button" : undefined}
                      title={isOrganizer ? "Click to edit" : undefined}
                    >
                      {o.location || "—"}
                    </span>
                  )
                )}
                {series?.rotation_mode && series.rotation_mode !== "none" && (
                  isOrganizer && editingHostId === o.occurrence_id ? (
                    <input
                      type="text"
                      className="form-input form-input-sm upcoming-host-input"
                      value={editingHostValue}
                      onChange={(e) => setEditingHostValue(e.target.value)}
                      autoFocus
                      placeholder="Host"
                      onBlur={async () => {
                        const newHost = editingHostValue.trim();
                        if (newHost === (o.host ?? "")) {
                          setEditingHostId(null);
                          return;
                        }
                        try {
                          // Auto-sync location when host_and_location mode is active
                          const patchPayload: Parameters<typeof patchOccurrence>[1] = {
                            host: newHost || null,
                          };
                          const hostAddress =
                            series?.rotation_mode === "host_and_location" && newHost
                              ? series.host_addresses?.[newHost]
                              : undefined;
                          if (hostAddress) {
                            patchPayload.location = hostAddress;
                          }
                          const updated = await patchOccurrence(o.occurrence_id, patchPayload);
                          setOccurrences((prev) =>
                            prev?.map((x) => (x.occurrence_id === o.occurrence_id ? updated : x)) ?? null,
                          );
                          // Show rotation prompt only if host is in the rotation list
                          if (newHost && series?.host_rotation?.includes(newHost)) {
                            const toastMsg = hostAddress
                              ? `Host updated to "${newHost}" · Location: ${hostAddress}`
                              : `Host updated to "${newHost}"`;
                            setToast({
                              message: toastMsg,
                              action: {
                                label: "Continue rotation from here →",
                                onClick: async () => {
                                  try {
                                    const result = await regenerateRotationFrom(seriesId!, o.occurrence_id);
                                    await load();
                                    setToast({
                                      message: `Updated ${result.updated_count} upcoming occurrences`,
                                    });
                                  } catch (err) {
                                    alert(err instanceof Error ? err.message : "Failed to regenerate rotation");
                                  }
                                },
                              },
                            });
                          }
                        } catch (err) {
                          alert(err instanceof Error ? err.message : "Failed to save");
                        }
                        setEditingHostId(null);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
                        if (e.key === "Escape") setEditingHostId(null);
                      }}
                    />
                  ) : (
                    <span
                      className={`upcoming-host${isOrganizer ? " upcoming-host-clickable" : ""}`}
                      onClick={isOrganizer ? () => {
                        setEditingHostId(o.occurrence_id);
                        setEditingHostValue(o.host ?? "");
                      } : undefined}
                      tabIndex={isOrganizer ? 0 : undefined}
                      role={isOrganizer ? "button" : undefined}
                      title={isOrganizer ? "Click to edit host" : undefined}
                    >
                      {o.host ? `Host: ${o.host}` : (isOrganizer ? "Set host" : "")}
                    </span>
                  )
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <ResourceLinks
        links={series?.links ?? null}
        canEdit={!!isOrganizer}
        onSave={async (links) => {
          if (!seriesId) return;
          const updated = await patchSeries(seriesId, { links });
          setSeries(updated);
        }}
      />

      {/* Completion Report — only shown when Done is enabled */}
      {series?.enable_done && <section className="section">
        <div className="section-header">
          <h2>Completion Report</h2>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => showReport ? setShowReport(false) : loadReport()}
            disabled={reportLoading}
          >
            {reportLoading ? "Loading..." : showReport ? "Hide" : "View report"}
          </button>
        </div>
        {showReport && report && (() => {
          const occs = report.occurrences.slice(-reportWindow);
          const occIds = new Set(occs.map((o) => o.occurrence_id));
          // Build lookup: occurrence_id -> set of user_ids who checked in
          const checkInMap = new Map<string, Set<string>>();
          for (const ci of report.check_ins) {
            if (!occIds.has(ci.occurrence_id)) continue;
            if (ci.status !== "confirmed") continue;
            if (!checkInMap.has(ci.occurrence_id)) checkInMap.set(ci.occurrence_id, new Set());
            checkInMap.get(ci.occurrence_id)!.add(ci.user_id);
          }
          // Get all members (non-organizer) as rows
          const allEntries = Object.entries(report.members);
          const nonOrganizers = allEntries.filter(([, role]) => role !== "organizer");
          // Solo self-study: show the organizer. Group: show only non-organizers.
          const visibleEntries = nonOrganizers.length > 0 ? nonOrganizers : allEntries;
          const members = visibleEntries
            .map(([uid, role]) => ({
              uid,
              role,
              name: report.member_profiles[uid]?.display_name ?? uid.slice(0, 8),
            }));
          members.sort((a, b) => a.name.localeCompare(b.name));
          return (
            <>
              <div className="report-controls">
                <label>
                  Show last{" "}
                  <select
                    value={reportWindow}
                    onChange={(e) => setReportWindow(Number(e.target.value))}
                    className="form-input form-input-sm report-window-select"
                  >
                    {[5, 10, 20, 50].map((n) => (
                      <option key={n} value={n}>{n}</option>
                    ))}
                  </select>
                  {" "}occurrences
                </label>
              </div>
              <div className="report-table-wrap">
                <table className="report-table">
                  <thead>
                    <tr>
                      <th className="report-name-col">Name</th>
                      {occs.map((o) => (
                        <th key={o.occurrence_id} className="report-date-col">
                          <Link to={occurrencePath(o.occurrence_id)}>
                            {formatShortDate(o.scheduled_for, room?.timezone)}
                          </Link>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {members.map((m) => (
                      <tr key={m.uid}>
                        <td className="report-name-col">{m.name}</td>
                        {occs.map((o) => {
                          const done = checkInMap.get(o.occurrence_id)?.has(m.uid);
                          return (
                            <td key={o.occurrence_id} className={`report-cell ${done ? "report-cell-done" : "report-cell-miss"}`}>
                              {done ? "✓" : "—"}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          );
        })()}
      </section>}

      {toast && <Toast {...toast} onDismiss={() => setToast(null)} />}

    </div>
  );
}
