import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { acceptInvite } from "../api";
import { LoadingSpinner } from "../components/LoadingSpinner";

export function AcceptInvite() {
  const { inviteId } = useParams<{ inviteId: string }>();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState(false);

  async function doAccept() {
    if (!inviteId) return;
    setStarted(true);
    setError(null);
    try {
      const result = await acceptInvite(inviteId);
      navigate(`/w/${result.workspace_id}`, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to accept invite");
    }
  }

  if (error) {
    return (
      <div className="workspace-view" style={{ textAlign: "center", paddingTop: "4rem" }}>
        <h2>Invite Error</h2>
        <p className="form-error">{error}</p>
        <button className="btn btn-primary btn-sm" onClick={doAccept}>
          Retry
        </button>
        <button
          className="btn btn-secondary btn-sm"
          style={{ marginLeft: "0.5rem" }}
          onClick={() => navigate("/dashboard")}
        >
          Go to Dashboard
        </button>
      </div>
    );
  }

  if (!started) {
    return (
      <div className="workspace-view" style={{ textAlign: "center", paddingTop: "4rem" }}>
        <h2>You've been invited!</h2>
        <p style={{ margin: "1rem 0", color: "var(--muted)" }}>Click below to join this workspace.</p>
        <button className="btn btn-primary" onClick={doAccept}>
          Accept Invite
        </button>
      </div>
    );
  }

  return <LoadingSpinner message="Accepting invite..." />;
}
