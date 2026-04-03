import { useEffect, useState, useCallback } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { timezonesMatch } from "../dateFormat";
import {
  getRoom,
  getRoomSeries,
  getRoomMembers,
  createRoomInvite,
  removeMember,
  createSeries,
  patchRoom,
  deleteRoom,
  getTelegramBot,
  connectTelegramBot,
  updateTelegramBotMode,
  deleteTelegramBot,
  generateTelegramLinkCode,
  type RoomSummary,
  type SeriesSummary,
  type ScheduleRule,
  type TelegramBotInfo,
} from "../api";
import { useAuth } from "../auth";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorMessage } from "../components/ErrorMessage";
import { Markdown } from "../components/Markdown";
import { ResourceLinks } from "../components/ResourceLinks";

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

export function RoomView() {
  const { roomId } = useParams<{ roomId: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [room, setRoom] = useState<RoomSummary | null>(null);
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
  const [formLocationType, setFormLocationType] = useState<"none" | "fixed" | "per_occurrence">("none");
  const [formCheckInDays, setFormCheckInDays] = useState<number[]>([]);
  const [formLink, setFormLink] = useState("");
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [editingTitle, setEditingTitle] = useState(false);
  const [editTitleValue, setEditTitleValue] = useState("");

  // Notes (room description)
  const [editingNotes, setEditingNotes] = useState(false);
  const [editNotesValue, setEditNotesValue] = useState("");
  const [notesSubmitting, setNotesSubmitting] = useState(false);

  // Members
  const [members, setMembers] = useState<Record<string, string> | null>(null);
  const [memberDetails, setMemberDetails] = useState<Record<string, { display_name: string | null; email: string | null }>>({});
  const [inviteLink, setInviteLink] = useState<string | null>(null);
  const [inviteRole, setInviteRole] = useState("participant");
  const [inviteCreating, setInviteCreating] = useState(false);
  const [removingUid, setRemovingUid] = useState<string | null>(null);

  // Telegram bot
  const [tgBot, setTgBot] = useState<TelegramBotInfo | null>(null);
  const [tgLoading, setTgLoading] = useState(true);
  const [tgToken, setTgToken] = useState("");
  const [tgMode, setTgMode] = useState<"read_only" | "read_write">("read_only");
  const [tgConnecting, setTgConnecting] = useState(false);
  const [tgError, setTgError] = useState<string | null>(null);
  const [tgLinkCode, setTgLinkCode] = useState<string | null>(null);
  const [tgLinkExpiry, setTgLinkExpiry] = useState(0);

  const load = useCallback(async () => {
    if (!roomId) return;
    setLoading(true);
    setError(null);
    setTgLoading(true);
    setTgError(null);
    try {
      const [rm, sr, mem] = await Promise.all([
        getRoom(roomId),
        getRoomSeries(roomId),
        getRoomMembers(roomId),
      ]);
      setRoom(rm);
      setSeries(sr);
      setMembers(mem.members);
      setMemberDetails(
        Object.fromEntries(
          (mem.member_details ?? []).map((member) => [
            member.uid,
            { display_name: member.display_name, email: member.email },
          ]),
        ),
      );
      // Load telegram bot (non-blocking)
      getTelegramBot(roomId).then(setTgBot).catch((err) => {
        console.error("Failed to load Telegram bot:", err);
        setTgError(err instanceof Error ? err.message : "Failed to load bot settings");
      }).finally(() => setTgLoading(false));
    } catch (err) {
      setError(err as Error);
      setTgLoading(false);
    } finally {
      setLoading(false);
    }
  }, [roomId]);

  useEffect(() => { load(); }, [load]);

  function toggleDay(day: number) {
    setFormDays((prev) => {
      const next = prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day];
      // Remove from check-in days if no longer a scheduled day
      if (!next.includes(day)) {
        setFormCheckInDays((ci) => ci.filter((d) => d !== day));
      }
      return next;
    });
  }

  function toggleCheckInDay(day: number) {
    setFormCheckInDays((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day],
    );
  }

  async function handleCreateSeries(e: React.FormEvent) {
    e.preventDefault();
    if (!roomId || !formTitle.trim()) return;
    setFormSubmitting(true);
    setFormError(null);

    let scheduleRule: ScheduleRule;
    if (formFreq === "weekly") {
      scheduleRule = { frequency: "weekly", weekdays: formDays.length > 0 ? formDays : [1] };
    } else {
      scheduleRule = { frequency: formFreq };
    }

    try {
      const created = await createSeries(roomId, {
        title: formTitle.trim(),
        description: formDescription.trim() || undefined,
        schedule_rule: scheduleRule,
        default_time: formTime || undefined,
        default_duration_minutes: formDuration ? parseInt(formDuration, 10) : undefined,
        default_location: formLocation.trim() || undefined,
        default_online_link: formLink.trim() || undefined,
        location_type: formLocationType,
        check_in_weekdays: formCheckInDays.length > 0 ? formCheckInDays : undefined,
      });
      setShowForm(false);
      setFormTitle("");
      setFormDescription("");
      setFormFreq("weekly");
      setFormDays([1]);
      setFormTime("10:00");
      setFormDuration("60");
      setFormLocation("");
      setFormLocationType("none");
      setFormCheckInDays([]);
      setFormLink("");
      // Navigate to series detail
      navigate(`/room/${roomId}/series/${created.series_id}`);
    } catch (err) {
      console.error("Failed to create series:", err);
      setFormError(err instanceof Error ? err.message : "Failed to create series");
    } finally {
      setFormSubmitting(false);
    }
  }

  async function handleCreateInvite() {
    if (!roomId) return;
    setInviteCreating(true);
    try {
      const invite = await createRoomInvite(roomId, inviteRole);
      setInviteLink(`${window.location.origin}/invites/${invite.invite_id}`);
    } catch (err) {
      console.error("Failed to create invite:", err);
      alert(err instanceof Error ? err.message : "Failed to create invite");
    } finally {
      setInviteCreating(false);
    }
  }

  async function handleRemoveMember(uid: string) {
    if (!roomId) return;
    const isSelf = uid === user?.uid;
    if (isSelf) {
      const otherOrganizers = members && Object.entries(members).some(
        ([id, r]) => id !== uid && r === "organizer",
      );
      if (!otherOrganizers) {
        alert("You are the only organizer. Add another organizer before leaving.");
        return;
      }
      if (!window.confirm("Leave this room? You will lose access.")) return;
    }
    setRemovingUid(uid);
    try {
      await removeMember(roomId, uid);
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
      console.error("Failed to remove member:", err);
      alert(err instanceof Error ? err.message : "Failed to remove member");
    } finally {
      setRemovingUid(null);
    }
  }

  // Telegram link code countdown
  useEffect(() => {
    if (tgLinkExpiry <= 0) return;
    const timer = setInterval(() => {
      setTgLinkExpiry((prev) => {
        if (prev <= 1) {
          setTgLinkCode(null);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [tgLinkExpiry > 0]);

  async function handleConnectBot(e: React.FormEvent) {
    e.preventDefault();
    if (!roomId || !tgToken.trim()) return;
    setTgConnecting(true);
    setTgError(null);
    try {
      const bot = await connectTelegramBot(roomId, tgToken.trim(), tgMode);
      setTgBot(bot);
      setTgToken("");
    } catch (err) {
      console.error("Failed to connect Telegram bot:", err);
      setTgError(err instanceof Error ? err.message : "Failed to connect bot");
    } finally {
      setTgConnecting(false);
    }
  }

  async function handleUpdateBotMode(mode: "read_only" | "read_write") {
    if (!roomId) return;
    setTgError(null);
    try {
      const bot = await updateTelegramBotMode(roomId, mode);
      setTgBot(bot);
    } catch (err) {
      console.error("Failed to update Telegram bot mode:", err);
      setTgError(err instanceof Error ? err.message : "Failed to update mode");
    }
  }

  async function handleDisconnectBot() {
    if (!roomId || !window.confirm("Disconnect the Telegram bot? Chat linking will stop.")) return;
    setTgError(null);
    try {
      await deleteTelegramBot(roomId);
      setTgBot(null);
      setTgLinkCode(null);
      setTgLinkExpiry(0);
    } catch (err) {
      console.error("Failed to disconnect Telegram bot:", err);
      setTgError(err instanceof Error ? err.message : "Failed to disconnect bot");
    }
  }

  async function handleGenerateLinkCode() {
    if (!roomId) return;
    setTgError(null);
    try {
      const { code, expires_in } = await generateTelegramLinkCode(roomId);
      setTgLinkCode(code);
      setTgLinkExpiry(expires_in);
    } catch (err) {
      console.error("Failed to generate Telegram link code:", err);
      setTgError(err instanceof Error ? err.message : "Failed to generate link code");
    }
  }

  const isOrganizer = user?.uid && room?.member_roles[user.uid] === "organizer";

  if (loading) return <LoadingSpinner message="Loading room..." />;
  if (error) return <ErrorMessage error={error} onRetry={load} />;

  return (
    <div className="room-view">
      <div className="page-header">
        <div className="page-header-top">
          <Link to="/dashboard" className="back-link">&larr; Dashboard</Link>
        </div>
        {isOrganizer && editingTitle ? (
          <form
            className="inline-edit-title"
            onSubmit={async (e) => {
              e.preventDefault();
              if (!roomId || !editTitleValue.trim()) return;
              try {
                const updated = await patchRoom(roomId, { title: editTitleValue.trim() });
                setRoom(updated);
                setEditingTitle(false);
              } catch (err) {
                console.error("Failed to rename room:", err);
                alert(err instanceof Error ? err.message : "Failed to rename");
              }
            }}
          >
            <input
              type="text"
              className="form-input page-title-input"
              value={editTitleValue}
              onChange={(e) => setEditTitleValue(e.target.value)}
              autoFocus
              required
            />
            <button type="submit" className="btn btn-primary btn-sm">Save</button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditingTitle(false)}>
              Cancel
            </button>
          </form>
        ) : (
          <h1
            className={`page-title${isOrganizer ? " page-title-editable" : ""}`}
            onClick={isOrganizer ? () => { setEditTitleValue(room?.title ?? ""); setEditingTitle(true); } : undefined}
            title={isOrganizer ? "Click to rename" : undefined}
          >
            {room?.title}
          </h1>
        )}
        {room && !timezonesMatch(room.timezone) && (
          <p className="page-meta-tz">{room.timezone}</p>
        )}
      </div>

      {/* Notes (room description) */}
      <section className="section">
        {editingNotes ? (
          <>
            <div className="section-header"><h2>Notes</h2></div>
            <div className="inline-edit-row" style={{ flexDirection: "column", alignItems: "stretch" }}>
              <textarea
                className="form-input form-textarea"
                value={editNotesValue}
                onChange={(e) => setEditNotesValue(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Escape") setEditingNotes(false); }}
                rows={3}
                placeholder="Add a description, resources, or notes for this room."
                disabled={notesSubmitting}
                autoFocus
              />
              <div className="form-actions">
                <button
                  className="btn btn-primary btn-sm"
                  disabled={notesSubmitting}
                  onClick={async () => {
                    if (!roomId) return;
                    setNotesSubmitting(true);
                    try {
                      const updated = await patchRoom(roomId, { description: editNotesValue.trim() || "" });
                      setRoom(updated);
                      setEditingNotes(false);
                    } catch (err) {
                      console.error("Failed to update room notes:", err);
                      alert(err instanceof Error ? err.message : "Failed to save");
                    } finally {
                      setNotesSubmitting(false);
                    }
                  }}
                >Save</button>
                <button className="btn btn-secondary btn-sm" onClick={() => setEditingNotes(false)} disabled={notesSubmitting}>Cancel</button>
              </div>
            </div>
          </>
        ) : room?.description ? (
          <>
            <div className="section-header"><h2>Notes</h2></div>
            <div
              className={isOrganizer ? "page-title-editable" : ""}
              onClick={isOrganizer ? () => { setEditNotesValue(room.description ?? ""); setEditingNotes(true); } : undefined}
              title={isOrganizer ? "Click to edit notes" : undefined}
            >
              <Markdown text={room.description} />
            </div>
          </>
        ) : isOrganizer ? (
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => { setEditNotesValue(""); setEditingNotes(true); }}
          >
            + Add notes
          </button>
        ) : null}
      </section>

      <section className="section">
        <div className="section-header">
          <h2>Recurring Series</h2>
          {isOrganizer && !showForm && (
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
            {formDays.length > 0 && (
              <div className="form-field">
                <label>Self-practice days (enable check-in)</label>
                <div className="days-toggle">
                  {DAYS.map((day, i) => {
                    const dv = DAY_VALUES[i];
                    if (!formDays.includes(dv)) return null;
                    return (
                      <button
                        key={day}
                        type="button"
                        className={`btn btn-day ${formCheckInDays.includes(dv) ? "btn-primary" : "btn-secondary"}`}
                        onClick={() => toggleCheckInDay(dv)}
                        disabled={formSubmitting}
                      >
                        {day}
                      </button>
                    );
                  })}
                </div>
                <span className="form-hint">Occurrences on these days will show a check-in button</span>
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
                  className={`btn btn-sm ${formLocationType === "none" ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => setFormLocationType("none")}
                  disabled={formSubmitting}
                >
                  None
                </button>
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
                  <Link to={`/room/${roomId}/series/${s.series_id}`} className="series-card-title">
                    {s.title}
                  </Link>
                  {/* status badge hidden – issue #114 */}
                </div>
                <p className="series-card-schedule">
                  {formatScheduleRule(s.schedule_rule)}
                  {s.default_time && ` at ${s.default_time}`}
                  {s.default_duration_minutes && ` (${s.default_duration_minutes}m)`}
                </p>
                {s.rotation_mode && s.rotation_mode !== "none" && (
                  <p className="series-card-meta">
                    <span className="rotation-chip">
                      🔄 {s.rotation_mode === "host_only" ? "Host rotation" : "Host + location rotation"}: {s.host_rotation?.length || 0} {s.host_rotation?.length === 1 ? "host" : "hosts"}
                    </span>
                  </p>
                )}
                {s.description && <Markdown text={s.description} className="series-card-desc" />}
                {s.location_type !== "none" && (s.default_location || s.default_online_link) && (
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
                    to={`/room/${roomId}/series/${s.series_id}`}
                    className="btn btn-secondary btn-sm"
                  >
                    View schedule
                  </Link>
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

      <ResourceLinks
        links={room?.links ?? null}
        canEdit={!!isOrganizer}
        onSave={async (links) => {
          if (!roomId) return;
          const updated = await patchRoom(roomId, { links });
          setRoom(updated);
        }}
      />

      {/* Members */}
      <section className="section">
        <div className="section-header">
          <h2>Members</h2>
        </div>
        {members && (
          <ul className="members-list">
            {Object.entries(members).map(([uid, role]) => (
              <li key={uid} className="member-item">
                <span className="member-uid">
                  {uid === user?.uid
                    ? "You"
                    : memberDetails[uid]?.display_name
                      || memberDetails[uid]?.email
                      || uid.slice(0, 8)}
                </span>
                <span className={`badge badge-role-${role}`}>{role}</span>
                {(isOrganizer || uid === user?.uid) && (
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
                    navigator.clipboard.writeText(inviteLink).catch((err) => {
                      console.warn("Clipboard write failed:", err);
                    });
                  }}
                >
                  Copy
                </button>
              </div>
            )}
          </div>
        )}
      </section>

      {isOrganizer && (
        <section className="section">
          <div className="section-header">
            <h2>AI Assistant (Telegram)</h2>
          </div>
          {tgLoading ? (
            <p className="placeholder">Loading bot settings...</p>
          ) : tgBot ? (
            <div className="telegram-bot-config">
              <div className="telegram-bot-info">
                <span className="telegram-bot-username">
                  <a href={`https://t.me/${tgBot.bot_username}`} target="_blank" rel="noreferrer">
                    @{tgBot.bot_username}
                  </a>
                </span>
                <span className={`badge ${tgBot.active ? "badge-role-teacher" : "badge-role-participant"}`}>
                  {tgBot.active ? "active" : "inactive"}
                </span>
              </div>
              <div className="form-field">
                <label>Mode</label>
                <div className="visibility-toggle">
                  <button
                    type="button"
                    className={`btn btn-sm ${tgBot.mode === "read_only" ? "btn-primary" : "btn-secondary"}`}
                    onClick={() => handleUpdateBotMode("read_only")}
                  >
                    Read-only
                  </button>
                  <button
                    type="button"
                    className={`btn btn-sm ${tgBot.mode === "read_write" ? "btn-primary" : "btn-secondary"}`}
                    onClick={() => handleUpdateBotMode("read_write")}
                  >
                    Read &amp; Write
                  </button>
                </div>
                <span className="form-hint">
                  {tgBot.mode === "read_only"
                    ? "Bot can answer questions, but it won’t propose write actions."
                    : "Bot can answer questions and propose changes for confirmation."}
                </span>
              </div>
              <div className="form-field">
                <label>Link a Telegram chat</label>
                {tgLinkCode ? (
                  <div className="invite-link-box">
                    <input
                      type="text"
                      className="form-input"
                      value={tgLinkCode}
                      readOnly
                      onFocus={(e) => e.target.select()}
                    />
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => navigator.clipboard.writeText(tgLinkCode).catch((err) => console.warn("Clipboard write failed:", err))}
                    >
                      Copy
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={handleGenerateLinkCode}
                  >
                    Generate Link Code
                  </button>
                )}
                {tgLinkCode && tgLinkExpiry > 0 && (
                  <span className="form-hint">
                    Send this code in a private chat with your bot. Expires in {Math.floor(tgLinkExpiry / 60)}:{String(tgLinkExpiry % 60).padStart(2, "0")}
                  </span>
                )}
              </div>
              {tgError && <p className="form-error">{tgError}</p>}
              <div className="form-actions">
                <button
                  type="button"
                  className="btn btn-sm btn-danger"
                  onClick={handleDisconnectBot}
                >
                  Disconnect bot
                </button>
              </div>
            </div>
          ) : (
            <form className="create-page-form" onSubmit={handleConnectBot}>
              <div className="form-field">
                <label htmlFor="tg-token">Bot Token</label>
                <input
                  id="tg-token"
                  type="text"
                  className="form-input"
                  value={tgToken}
                  onChange={(e) => setTgToken(e.target.value)}
                  placeholder="123456:ABC-DEF..."
                  required
                  disabled={tgConnecting}
                />
                <span className="form-hint">
                  Create a bot via <a href="https://t.me/BotFather" target="_blank" rel="noreferrer">@BotFather</a> and paste the token here
                </span>
              </div>
              <div className="form-field">
                <label>Mode</label>
                <div className="visibility-toggle">
                  <button
                    type="button"
                    className={`btn btn-sm ${tgMode === "read_only" ? "btn-primary" : "btn-secondary"}`}
                    onClick={() => setTgMode("read_only")}
                    disabled={tgConnecting}
                  >
                    Read-only
                  </button>
                  <button
                    type="button"
                    className={`btn btn-sm ${tgMode === "read_write" ? "btn-primary" : "btn-secondary"}`}
                    onClick={() => setTgMode("read_write")}
                    disabled={tgConnecting}
                  >
                    Read &amp; Write
                  </button>
                </div>
              </div>
              {tgError && <p className="form-error">{tgError}</p>}
              <div className="form-actions">
                <button
                  type="submit"
                  className="btn btn-primary btn-sm"
                  disabled={tgConnecting || !tgToken.trim()}
                >
                  {tgConnecting ? "Connecting..." : "Connect Bot"}
                </button>
              </div>
            </form>
          )}
        </section>
      )}

      {isOrganizer && (
        <section className="section">
          <div className="section-header">
            <h2>Danger Zone</h2>
          </div>
          <button
            className="btn btn-sm btn-danger"
            onClick={async () => {
              if (!confirm("Delete this room and all its data? This cannot be undone.")) return;
              try {
                await deleteRoom(roomId!);
                navigate("/");
              } catch (err) {
                console.error("Failed to delete room:", err);
                alert(err instanceof Error ? err.message : "Failed to delete room");
              }
            }}
          >
            Delete room
          </button>
        </section>
      )}

    </div>
  );
}
