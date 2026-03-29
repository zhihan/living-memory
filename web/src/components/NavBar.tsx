import { Link } from "react-router-dom";
import { useAuth } from "../auth";

export function NavBar() {
  const { user, signOut } = useAuth();

  return (
    <nav className="navbar">
      <Link to="/dashboard" className="navbar-brand">
        Meeting Assistant
      </Link>
      {user && (
        <div className="navbar-user">
          <span className="navbar-email">
            {user.email || user.displayName || "Signed in"}
          </span>
          <button type="button" onClick={signOut} className="btn btn-secondary btn-sm">
            Sign out
          </button>
        </div>
      )}
    </nav>
  );
}
