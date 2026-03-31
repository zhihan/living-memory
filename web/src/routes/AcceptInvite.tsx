import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { acceptInvite } from "../api";
import { LoadingSpinner } from "../components/LoadingSpinner";

const ACCEPT_INVITE_TIMEOUT_MS = 15000;

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
      const result = await Promise.race([
        acceptInvite(inviteId),
        new Promise<never>((_, reject) => {
          window.setTimeout(() => {
            reject(new Error("Invite acceptance timed out. Retry or open Dashboard to check whether it already succeeded."));
          }, ACCEPT_INVITE_TIMEOUT_MS);
        }),
      ]);
      navigate(`/w/${result.workspace_id}`, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to accept invite");
    }
  }

  if (error) {
    return (
      <div className="invite-page">
        <h2>Invite Error</h2>
        <p className="form-error">{error}</p>
        <div className="invite-actions">
          <button className="btn btn-primary btn-sm" onClick={doAccept}>
            Retry
          </button>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => navigate("/dashboard")}
          >
            Go to Dashboard
          </button>
        </div>
      </div>
    );
  }

  if (!started) {
    return (
      <div className="invite-page">
        <h2>You've been invited!</h2>
        <p>Click below to join this workspace.</p>
        <button className="btn btn-primary" onClick={doAccept}>
          Accept Invite
        </button>
      </div>
    );
  }

  return <LoadingSpinner message="Accepting invite..." />;
}
