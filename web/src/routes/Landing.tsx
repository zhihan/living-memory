import { Navigate } from "react-router-dom";
import { useAuth } from "../auth";

export function Landing() {
  const { user, loading, signIn } = useAuth();

  if (loading) {
    return <div className="loading-screen">Loading...</div>;
  }

  if (user) {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <div className="landing">
      <h1>Meeting Assistant</h1>
      <p>Organize your recurring meetings with ease.</p>
      <button type="button" onClick={signIn} className="btn btn-primary">
        Sign in with Google
      </button>
    </div>
  );
}
