import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { acceptInvite } from "../api";
import { LoadingSpinner } from "../components/LoadingSpinner";

export function AcceptInvite() {
  const { inviteId } = useParams<{ inviteId: string }>();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!inviteId) return;
    acceptInvite(inviteId)
      .then((result) => {
        navigate(`/w/${result.workspace_id}`);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to accept invite");
      });
  }, [inviteId, navigate]);

  if (error) {
    return (
      <div className="workspace-view" style={{ textAlign: "center", paddingTop: "4rem" }}>
        <h2>Invite Error</h2>
        <p className="form-error">{error}</p>
        <button className="btn btn-primary btn-sm" onClick={() => navigate("/dashboard")}>
          Go to Dashboard
        </button>
      </div>
    );
  }

  return <LoadingSpinner message="Accepting invite..." />;
}
