import { useEffect, useState, useCallback } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import {
  getWorkspace,
  getWorkspaceSeries,
  getWorkspaceMembers,
  createWorkspaceInvite,
  removeMember,
  createSeries,
  generateOccurrences,
  type WorkspaceSummary,
  type SeriesSummary,
  type ScheduleRule,
} from "../api";
import { useAuth } from "../auth";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorMessage } from "../components/ErrorMessage";
import { AssistantChat } from "../AssistantChat";
import { Markdown } from "../components/Markdown";

const FREQ_OPTIONS = [
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "weekdays", label: "Weekdays (Mon-Fri)" },
];

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
// ISO weekday integers 1=Mon..7=Sun
const DAY_VALUES = [1, 2, 3, 4, 5, 6, 7];

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

export function WorkspaceView() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [workspace, setWorkspace] = useState<WorkspaceSummary | null>(null);
  const [series, setSeries] = useState<SeriesSummary[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [formTitle, setFormTitle] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formFreq, setFormFreq] = useState("weekly");
  const [formDays, setFormDays] = useState<number[]>([1]);
  const [formTime, setFormTime] = useState("10:00");
  const [formDuration, setFormDuration] = useState("60");
  const [formLocation, setFormLocation] = useState("");
  const [formLocationType, setFormLocationType] = useState<"fixed" | "per_occurrence">("fixed");
  const [formLink, setFormLink] = useState("");
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [generatingId, setGeneratingId] = useState<string | null>(null);
  const [showAssistant, setShowAssistant] = useState(false);

  // Members
  const [members, setMembers] = useState<Record<string, string> | null>(null);
  const [inviteLink, setInviteLink] = useState<string | null>(null);
  const [inviteRole, setInviteRole] = useState("participant");
  const [inviteCreating, setInviteCreating] = useState(false);
  const [removingUid, setRemovingUid] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    setError(null);
    try {
      const [ws, sr, mem] = await Promise.all([
        getWorkspace(workspaceId),
        getWorkspaceSeries(workspaceId),
        getWorkspaceMembers(workspaceId),
      ]);
      setWorkspace(ws);
      setSeries(sr);
      setMembers(mem.members);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => { load(); }, [load]);

  function toggleDay(day: number) {
    setFormDays((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day],
    );
  }

  async function handleCreateSeries(e: React.FormEvent) {
    e.preventDefault();
    if (!workspaceId || !formTitle.trim()) return;
    setFormSubmitting(true);
    setFormError(null);

    let scheduleRule: ScheduleRule;
    if (formFreq === "weekly") {
      scheduleRule = { frequency: "weekly", weekdays: formDays.length > 0 ? formDays : [1] };
    } else {
      scheduleRule = { frequency: formFreq };
    }

    try {
      const created = await createSeries(workspaceId, {
        title: formTitle.trim(),
        description: formDescription.trim() || undefined,
        schedule_rule: scheduleRule,
        default_time: formTime || undefined,
        default_duration_minutes: formDuration ? parseInt(formDuration, 10) : undefined,
        default_location: formLocation.trim() || undefined,
        default_online_link: formLink.trim() || undefined,
        location_type: formLocationType,
      });
      setShowForm(false);
      setFormTitle("");
      setFormDescription("");
      setFormFreq("weekly");
      setFormDays([1]);
      setFormTime("10:00");
      setFormDuration("60");
      setFormLocation("");
      setFormLocationType("fixed");
      setFormLink("");
      // Navigate to series detail
      navigate(`/w/${workspaceId}/series/${created.series_id}`);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to create series");
    } finally {
      setFormSubmitting(false);
    }
  }

  async function handleGenerate(seriesId: string) {
    setGeneratingId(seriesId);
    try {
      await generateOccurrences(seriesId, 60);
      navigate(`/w/${workspaceId}/series/${seriesId}`);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to generate occurrences");
    } finally {
      setGeneratingId(null);
    }
  }

  async function handleCreateInvite() {
    if (!workspaceId) return;
    setInviteCreating(true);
    try {
      const invite = await createWorkspaceInvite(workspaceId, inviteRole);
      setInviteLink(`${window.location.origin}/invites/${invite.invite_id}`);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to create invite");
    } finally {
      setInviteCreating(false);
    }
  }

  async function handleRemoveMember(uid: string) {
    if (!workspaceId) return;
    const isSelf = uid === user?.uid;
    if (isSelf && !window.confirm("Leave this workspace? You will lose access.")) return;
    setRemovingUid(uid);
    try {
      await removeMember(workspaceId, uid);
      if (isSelf) {
        navigate("/dashboard");
        return;
      }
      setMembers((prev) => {
        if (!prev) return prev;
        const next = { ...prev };
        delete next[uid];
        return next;
      });
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to remove member");
    } finally {
      setRemovingUid(null);
    }
  }

  const isOrganizer = user?.uid && workspace?.member_roles[user.uid] === "organizer";

  if (loading) return <LoadingSpinner message="Loading workspace..." />;
  if (error) return <ErrorMessage error={error} onRetry={load} />;

  return (
    <div className="workspace-view">
      <div className="page-header">
        <div className="page-header-top">
          <Link to="/dashboard" className="back-link">&larr; Dashboard</Link>
        </div>
        <h1 className="page-title">
          {workspace?.title}
        </h1>
        {workspace && (
          <p className="page-meta-tz">{workspace.timezone}</p>
        )}
      </div>

      <section className="section">
        <div className="section-header">
          <h2>Recurring Series</h2>
          {!showForm && (
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => setShowForm(true)}
            >
              + New Series
            </button>
          )}
        </div>

        {showForm && (
          <form className="create-page-form" onSubmit={handleCreateSeries}>
            <div className="form-field">
              <label htmlFor="series-title">Title</label>
              <input
                id="series-title"
                type="text"
                className="form-input"
                value={formTitle}
                onChange={(e) => setFormTitle(e.target.value)}
                placeholder="e.g. Weekly Standup"
                required
                autoFocus
                disabled={formSubmitting}
              />
            </div>
            <div className="form-field">
              <label htmlFor="series-desc">Description (markdown supported)</label>
              <textarea
                id="series-desc"
                className="form-input form-textarea"
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
                placeholder={"Add resources, links, and notes.\ne.g. [Study Guide](https://example.com)"}
                disabled={formSubmitting}
                rows={3}
              />
            </div>
            <div className="form-field">
              <label>Frequency</label>
              <div className="visibility-toggle">
                {FREQ_OPTIONS.map((f) => (
                  <button
                    key={f.value}
                    type="button"
                    className={`btn btn-sm ${formFreq === f.value ? "btn-primary" : "btn-secondary"}`}
                    onClick={() => setFormFreq(f.value)}
                    disabled={formSubmitting}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>
            {formFreq === "weekly" && (
              <div className="form-field">
                <label>Days of Week</label>
                <div className="days-toggle">
                  {DAYS.map((day, i) => (
                    <button
                      key={day}
                      type="button"
                      className={`btn btn-day ${formDays.includes(DAY_VALUES[i]) ? "btn-primary" : "btn-secondary"}`}
                      onClick={() => toggleDay(DAY_VALUES[i])}
                      disabled={formSubmitting}
                    >
                      {day}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="form-row">
              <div className="form-field form-field-half">
                <label htmlFor="series-time">Start Time</label>
                <input
                  id="series-time"
                  type="time"
                  className="form-input"
                  value={formTime}
                  onChange={(e) => setFormTime(e.target.value)}
                  disabled={formSubmitting}
                />
              </div>
              <div className="form-field form-field-half">
                <label htmlFor="series-duration">Duration (min)</label>
                <input
                  id="series-duration"
                  type="number"
                  className="form-input"
                  value={formDuration}
                  onChange={(e) => setFormDuration(e.target.value)}
                  min="5"
                  max="480"
                  disabled={formSubmitting}
                />
              </div>
            </div>
            <div className="form-field">
              <label>Location type</label>
              <div className="visibility-toggle">
                <button
                  type="button"
                  className={`btn btn-sm ${formLocationType === "fixed" ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => setFormLocationType("fixed")}
                  disabled={formSubmitting}
                >
                  Fixed location
                </button>
                <button
                  type="button"
                  className={`btn btn-sm ${formLocationType === "per_occurrence" ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => setFormLocationType("per_occurrence")}
                  disabled={formSubmitting}
                >
                  Changes each meeting
                </button>
              </div>
            </div>
            {formLocationType === "fixed" && (
              <div className="form-field">
                <label htmlFor="series-location">Default location</label>
                <input
                  id="series-location"
                  type="text"
                  className="form-input"
                  value={formLocation}
                  onChange={(e) => setFormLocation(e.target.value)}
                  placeholder="Room 3B or 123 Main St"
                  disabled={formSubmitting}
                />
              </div>
            )}
            <div className="form-field">
              <label htmlFor="series-link">Online Link</label>
              <input
                id="series-link"
                type="url"
                className="form-input"
                value={formLink}
                onChange={(e) => setFormLink(e.target.value)}
                placeholder="https://zoom.us/j/..."
                disabled={formSubmitting}
              />
            </div>
            {formError && <p className="form-error">{formError}</p>}
            <div className="form-actions">
              <button
                type="submit"
                className="btn btn-primary btn-sm"
                disabled={formSubmitting || !formTitle.trim()}
              >
                {formSubmitting ? "Creating..." : "Create Series"}
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

        {series && series.length > 0 ? (
          <ul className="series-list">
            {series.map((s) => (
              <li key={s.series_id} className="series-card">
                <div className="series-card-top">
                  <Link to={`/w/${workspaceId}/series/${s.series_id}`} className="series-card-title">
                    {s.title}
                  </Link>
                  <span className={`badge badge-status-${s.status}`}>{s.status}</span>
                </div>
                <p className="series-card-schedule">
                  {formatScheduleRule(s.schedule_rule)}
                  {s.default_time && ` at ${s.default_time}`}
                  {s.default_duration_minutes && ` (${s.default_duration_minutes}m)`}
                </p>
                {s.description && <Markdown text={s.description} className="series-card-desc" />}
                {(s.default_location || s.default_online_link) && (
                  <p className="series-card-location">
                    {s.default_location && (
                      <span className="location-chip">{s.default_location}</span>
                    )}
                    {s.default_online_link && (
                      <a
                        href={s.default_online_link}
                        target="_blank"
                        rel="noreferrer"
                        className="link-chip"
                      >
                        Join online
                      </a>
                    )}
                  </p>
                )}
                <div className="series-card-actions">
                  <Link
                    to={`/w/${workspaceId}/series/${s.series_id}`}
                    className="btn btn-secondary btn-sm"
                  >
                    View schedule
                  </Link>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => handleGenerate(s.series_id)}
                    disabled={generatingId === s.series_id}
                  >
                    {generatingId === s.series_id ? "Generating..." : "Generate occurrences"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          !showForm && (
            <p className="placeholder">
              No series yet. Create a recurring schedule to get started.
            </p>
          )
        )}
      </section>

      {/* Members */}
      <section className="section">
        <div className="section-header">
          <h2>Members</h2>
        </div>
        {members && (
          <ul className="members-list">
            {Object.entries(members).map(([uid, role]) => (
              <li key={uid} className="member-item">
                <span className="member-uid">{uid === user?.uid ? "You" : uid.slice(0, 8)}</span>
                <span className={`badge badge-role-${role}`}>{role}</span>
                {isOrganizer && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-xs"
                    onClick={() => handleRemoveMember(uid)}
                    disabled={removingUid === uid}
                  >
                    {removingUid === uid ? "Removing..." : uid === user?.uid ? "Leave" : "Remove"}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
        {isOrganizer && (
          <div className="invite-section">
            <div className="invite-controls">
              <select
                className="form-input form-input-inline"
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value)}
              >
                <option value="participant">Participant</option>
                <option value="organizer">Organizer</option>
              </select>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={handleCreateInvite}
                disabled={inviteCreating}
              >
                {inviteCreating ? "Creating..." : "Create Invite Link"}
              </button>
            </div>
            {inviteLink && (
              <div className="invite-link-box">
                <input
                  type="text"
                  className="form-input"
                  value={inviteLink}
                  readOnly
                  onFocus={(e) => e.target.select()}
                />
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => {
                    navigator.clipboard.writeText(inviteLink);
                  }}
                >
                  Copy
                </button>
              </div>
            )}
          </div>
        )}
      </section>

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
          <AssistantChat workspaceId={workspaceId} />
        )}
      </section>
    </div>
  );
}
