import { useEffect, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import {
  getPage,
  getPageMemories,
  type PageSummary,
  type MemoryItem,
} from "../api";
import { useAuth } from "../auth";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorMessage } from "../components/ErrorMessage";
import { MemoryList } from "../components/MemoryList";
import { AddMemoryForm } from "../components/AddMemoryForm";

export function PageView() {
  const { slug } = useParams<{ slug: string }>();
  const { user } = useAuth();
  const [page, setPage] = useState<PageSummary | null>(null);
  const [memories, setMemories] = useState<MemoryItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const load = useCallback(async () => {
    if (!slug) return;
    setLoading(true);
    setError(null);
    try {
      const [p, m] = await Promise.all([
        getPage(slug),
        getPageMemories(slug),
      ]);
      setPage(p);
      setMemories(m);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <LoadingSpinner message="Loading page..." />;
  if (error) return <ErrorMessage error={error} onRetry={load} />;

  return (
    <div className="page-view">
      <div className="page-header">
        <div className="page-header-top">
          <Link to="/dashboard" className="back-link">
            &larr; Dashboard
          </Link>
          {slug && user && page?.owner_uids.includes(user.uid) && (
            <Link to={`/p/${slug}/settings`} className="back-link">
              Settings
            </Link>
          )}
        </div>
        <h1>
          {page?.title}
          <span className={`badge badge-${page?.visibility}`}>
            {page?.visibility}
          </span>
        </h1>
      </div>

      {memories && memories.length > 0 ? (
        <MemoryList memories={memories} />
      ) : (
        <p className="placeholder">No upcoming events on this page.</p>
      )}

      {slug && user && page?.owner_uids.includes(user.uid) && (
        <AddMemoryForm slug={slug} onSuccess={load} />
      )}
    </div>
  );
}
