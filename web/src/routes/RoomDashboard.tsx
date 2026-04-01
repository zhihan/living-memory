import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import {
  getMyRooms,
  createRoom,
  type RoomSummary,
  type ScheduleRule,
} from "../api";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorMessage } from "../components/ErrorMessage";
import { TimezoneSelect } from "../components/TimezoneSelect";

export function RoomDashboard() {
  const [rooms, setRooms] = useState<RoomSummary[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [formTitle, setFormTitle] = useState("");
  const [formTimezone, setFormTimezone] = useState(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  );
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rs = await getMyRooms();
      setRooms(rs);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!formTitle.trim()) return;
    setFormSubmitting(true);
    setFormError(null);
    try {
      await createRoom(formTitle.trim(), "shared", formTimezone);
      setShowForm(false);
      setFormTitle("");
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to create room");
    } finally {
      setFormSubmitting(false);
    }
  }

  if (loading) return <LoadingSpinner message="Loading rooms..." />;
  if (error) return <ErrorMessage error={error} onRetry={load} />;

  return (
    <div className="dashboard">
      <section className="section">
        <div className="section-header">
          <h2>My Rooms</h2>
          {!showForm && (
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => setShowForm(true)}
            >
              + New
            </button>
          )}
        </div>

        {showForm && (
          <form className="create-page-form" onSubmit={handleCreate}>
            <div className="form-field">
              <label htmlFor="rm-title">Name</label>
              <input
                id="rm-title"
                type="text"
                className="form-input"
                value={formTitle}
                onChange={(e) => setFormTitle(e.target.value)}
                placeholder="e.g. Weekly Team Sync"
                required
                autoFocus
                disabled={formSubmitting}
              />
            </div>
            <div className="form-field">
              <label htmlFor="rm-tz">Timezone</label>
              <TimezoneSelect
                id="rm-tz"
                value={formTimezone}
                onChange={setFormTimezone}
              />
            </div>
            {formError && <p className="form-error">{formError}</p>}
            <div className="form-actions">
              <button
                type="submit"
                className="btn btn-primary btn-sm"
                disabled={formSubmitting || !formTitle.trim()}
              >
                {formSubmitting ? "Creating..." : "Create"}
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => { setShowForm(false); setFormError(null); }}
                disabled={formSubmitting}
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        {rooms && rooms.length > 0 ? (
          <ul className="page-list">
            {rooms.map((rm) => (
              <RoomCard key={rm.room_id} room={rm} />
            ))}
          </ul>
        ) : (
          !showForm && (
            <p className="placeholder">
              No rooms yet. Create one to start scheduling.
            </p>
          )
        )}
      </section>
    </div>
  );
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

function seriesSubtitle(room: RoomSummary): string {
  const count = room.series_count ?? 0;
  if (count === 0) return "No series";
  if (count === 1 && room.series_schedule) {
    let text = formatScheduleRule(room.series_schedule);
    if (room.series_default_time) text += ` at ${room.series_default_time}`;
    return text;
  }
  return `${count} series`;
}

function RoomCard({ room }: { room: RoomSummary }) {
  const isParticipant = room.my_role && room.my_role !== "organizer";
  return (
    <li className="page-card room-card">
      <Link to={`/room/${room.room_id}`}>
        <strong>{room.title}</strong>
        {isParticipant && (
          <span className="role-badge role-participant">{room.my_role}</span>
        )}
      </Link>
      <p className="page-meta-tz">{seriesSubtitle(room)}</p>
    </li>
  );
}
