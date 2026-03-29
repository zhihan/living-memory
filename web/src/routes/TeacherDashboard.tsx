import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  getCohortDashboard,
  addCohortMember,
  type CohortDashboard,
  type StudentSummary,
} from "../api";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorMessage } from "../components/ErrorMessage";

function EscalationBadge({ level }: { level: string }) {
  if (level === "escalate") {
    return (
      <span className="badge badge-red" title="Escalation required">
        🚨 Escalate
      </span>
    );
  }
  if (level === "nudge") {
    return (
      <span className="badge badge-yellow" title="Consider a nudge">
        ⚠️ Nudge
      </span>
    );
  }
  return (
    <span className="badge badge-green" title="On track">
      ✅ OK
    </span>
  );
}

function StreakBar({ current, longest }: { current: number; longest: number }) {
  return (
    <div className="streak-bar">
      <span className="streak-current">🔥 {current} day streak</span>
      {longest > current && (
        <span className="streak-best"> (best: {longest})</span>
      )}
    </div>
  );
}

function StudentRow({ student }: { student: StudentSummary }) {
  return (
    <tr className={`student-row escalation-${student.escalation.level}`}>
      <td className="student-id" title={student.user_id}>
        {student.user_id.slice(0, 8)}…
      </td>
      <td>
        <StreakBar
          current={student.streak.current_streak}
          longest={student.streak.longest_streak}
        />
      </td>
      <td>{student.streak.total_confirmed}</td>
      <td>
        <EscalationBadge level={student.escalation.level} />
      </td>
      <td>
        {student.badges.length > 0
          ? student.badges.join(", ")
          : <span className="muted">none</span>}
      </td>
    </tr>
  );
}

function DashboardView({
  dashboard,
}: {
  dashboard: CohortDashboard;
}) {
  const escalated = dashboard.students.filter(
    (s) => s.escalation.level === "escalate"
  );
  const nudge = dashboard.students.filter(
    (s) => s.escalation.level === "nudge"
  );

  return (
    <div className="dashboard-view">
      <div className="dashboard-stats">
        <div className="stat-card">
          <div className="stat-value">{dashboard.total_members}</div>
          <div className="stat-label">Students</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{dashboard.avg_current_streak.toFixed(1)}</div>
          <div className="stat-label">Avg Streak</div>
        </div>
        <div className="stat-card stat-card-warning">
          <div className="stat-value">{dashboard.total_misses_this_week}</div>
          <div className="stat-label">Misses (7 days)</div>
        </div>
        <div className="stat-card stat-card-danger">
          <div className="stat-value">{escalated.length}</div>
          <div className="stat-label">Need Review</div>
        </div>
      </div>

      {escalated.length > 0 && (
        <div className="alert alert-danger">
          <strong>🚨 {escalated.length} student(s) need teacher review:</strong>{" "}
          {escalated.map((s) => s.user_id.slice(0, 8)).join(", ")}
        </div>
      )}

      {nudge.length > 0 && (
        <div className="alert alert-warning">
          <strong>⚠️ {nudge.length} student(s) could use a nudge:</strong>{" "}
          {nudge.map((s) => s.user_id.slice(0, 8)).join(", ")}
        </div>
      )}

      <table className="students-table">
        <thead>
          <tr>
            <th>Student</th>
            <th>Streak</th>
            <th>Total Check-ins</th>
            <th>Status</th>
            <th>Badges</th>
          </tr>
        </thead>
        <tbody>
          {dashboard.students.length === 0 ? (
            <tr>
              <td colSpan={5} className="muted center">
                No students in this cohort yet.
              </td>
            </tr>
          ) : (
            dashboard.students.map((s) => (
              <StudentRow key={s.user_id} student={s} />
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export function TeacherDashboard() {
  const { cohortId } = useParams<{ cohortId: string }>();

  const [dashboard, setDashboard] = useState<CohortDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  // Add-member form
  const [showAddMember, setShowAddMember] = useState(false);
  const [newMemberUid, setNewMemberUid] = useState("");
  const [addingMember, setAddingMember] = useState(false);
  const [addMemberError, setAddMemberError] = useState<string | null>(null);

  const load = () => {
    if (!cohortId) return;
    setLoading(true);
    setError(null);
    getCohortDashboard(cohortId)
      .then(setDashboard)
      .catch(setError)
      .finally(() => setLoading(false));
  };

  useEffect(load, [cohortId]);

  const handleAddMember = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cohortId || !newMemberUid.trim()) return;
    setAddingMember(true);
    setAddMemberError(null);
    try {
      await addCohortMember(cohortId, newMemberUid.trim());
      setNewMemberUid("");
      setShowAddMember(false);
      load();
    } catch (err: unknown) {
      setAddMemberError(err instanceof Error ? err.message : "Failed to add member");
    } finally {
      setAddingMember(false);
    }
  };

  if (!cohortId) return <ErrorMessage error={new Error("No cohort ID provided")} />;

  return (
    <div className="teacher-dashboard">
      <div className="page-header">
        <h1>
          {dashboard ? dashboard.cohort_title : "Cohort Dashboard"}
        </h1>
        <div className="header-actions">
          <button
            className="btn btn-secondary"
            onClick={() => setShowAddMember((v) => !v)}
          >
            + Add Student
          </button>
          <button className="btn btn-ghost" onClick={load}>
            ↻ Refresh
          </button>
        </div>
      </div>

      {showAddMember && (
        <form className="add-member-form" onSubmit={handleAddMember}>
          <label>
            Student UID:
            <input
              type="text"
              value={newMemberUid}
              onChange={(e) => setNewMemberUid(e.target.value)}
              placeholder="Firebase UID"
              required
            />
          </label>
          {addMemberError && (
            <span className="form-error">{addMemberError}</span>
          )}
          <button type="submit" className="btn btn-primary" disabled={addingMember}>
            {addingMember ? "Adding…" : "Add Student"}
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => setShowAddMember(false)}
          >
            Cancel
          </button>
        </form>
      )}

      {loading && <LoadingSpinner />}
      {error && <ErrorMessage error={error} />}
      {!loading && !error && dashboard && (
        <DashboardView dashboard={dashboard} />
      )}
    </div>
  );
}
