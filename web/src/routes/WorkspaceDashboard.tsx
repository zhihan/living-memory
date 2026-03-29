import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import {
  getMyWorkspaces,
  createWorkspace,
  type WorkspaceSummary,
} from "../api";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorMessage } from "../components/ErrorMessage";
import { TimezoneSelect } from "../components/TimezoneSelect";

const WORKSPACE_TYPES = [
  { value: "meeting", label: "Meeting" },
  { value: "reminder", label: "Reminder" },
  { value: "study", label: "Study" },
];

export function WorkspaceDashboard() {
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [formTitle, setFormTitle] = useState("");
  const [formType, setFormType] = useState("meeting");
  const [formTimezone, setFormTimezone] = useState(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  );
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const ws = await getMyWorkspaces();
      setWorkspaces(ws);
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
      await createWorkspace(formTitle.trim(), formType, formTimezone);
      setShowForm(false);
      setFormTitle("");
      setFormType("meeting");
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to create workspace");
    } finally {
      setFormSubmitting(false);
    }
  }

  if (loading) return <LoadingSpinner message="Loading workspaces..." />;
  if (error) return <ErrorMessage error={error} onRetry={load} />;

  return (
    <div className="dashboard">
      <section className="section">
        <div className="section-header">
          <h2>My Workspaces</h2>
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
              <label htmlFor="ws-title">Name</label>
              <input
                id="ws-title"
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
              <label>Type</label>
              <div className="visibility-toggle">
                {WORKSPACE_TYPES.map((t) => (
                  <button
                    key={t.value}
                    type="button"
                    className={`btn btn-sm ${formType === t.value ? "btn-primary" : "btn-secondary"}`}
                    onClick={() => setFormType(t.value)}
                    disabled={formSubmitting}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="form-field">
              <label htmlFor="ws-tz">Timezone</label>
              <TimezoneSelect
                id="ws-tz"
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

        {workspaces && workspaces.length > 0 ? (
          <ul className="page-list">
            {workspaces.map((ws) => (
              <WorkspaceCard key={ws.workspace_id} workspace={ws} />
            ))}
          </ul>
        ) : (
          !showForm && (
            <p className="placeholder">
              No workspaces yet. Create one to start scheduling.
            </p>
          )
        )}
      </section>
    </div>
  );
}

function WorkspaceCard({ workspace }: { workspace: WorkspaceSummary }) {
  const typeLabel = workspace.type.charAt(0).toUpperCase() + workspace.type.slice(1);
  return (
    <li className="page-card workspace-card">
      <Link to={`/w/${workspace.workspace_id}`}>
        <strong>{workspace.title}</strong>
        <span className={`badge badge-${workspace.type}`}>{typeLabel}</span>
      </Link>
      <p className="page-meta-tz">{workspace.timezone}</p>
    </li>
  );
}
