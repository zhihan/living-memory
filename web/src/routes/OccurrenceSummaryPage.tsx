import { useEffect, useState, useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import {
  getOccurrence,
  getSeries,
  type OccurrenceSummary,
  type SeriesSummary,
} from "../api";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorMessage } from "../components/ErrorMessage";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function OccurrenceSummaryPage() {
  const { occurrenceId } = useParams<{ occurrenceId: string }>();

  const [occurrence, setOccurrence] = useState<OccurrenceSummary | null>(null);
  const [series, setSeries] = useState<SeriesSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    if (!occurrenceId) return;
    setLoading(true);
    setError(null);
    try {
      const occ = await getOccurrence(occurrenceId);
      const s = await getSeries(occ.series_id);
      setOccurrence(occ);
      setSeries(s);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [occurrenceId]);

  useEffect(() => { load(); }, [load]);

  async function handleCopy() {
    await navigator.clipboard.writeText(window.location.href);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (loading) return <LoadingSpinner message="Loading meeting details..." />;
  if (error) return <ErrorMessage error={error} onRetry={load} />;

  const occ = occurrence!;
  const effectiveTitle = occ.overrides?.title ?? series?.title ?? "Meeting";
  const effectiveLocation = occ.location ?? occ.overrides?.location ?? series?.default_location;
  const effectiveLink = occ.overrides?.online_link ?? series?.default_online_link;
  const effectiveNotes = occ.overrides?.notes;
  const effectiveDuration = occ.overrides?.duration_minutes ?? series?.default_duration_minutes;

  const isCancelled = occ.status === "cancelled" || occ.status === "skipped";

  return (
    <div className="summary-page">
      {isCancelled && (
        <div className="summary-cancelled-banner">
          This meeting has been {occ.status}.
        </div>
      )}

      <div className="summary-hero">
        <h1 className="summary-title">{effectiveTitle}</h1>
        <p className="summary-date">{formatDate(occ.scheduled_for)}</p>
        {effectiveDuration && (
          <p className="summary-duration">{effectiveDuration} minutes</p>
        )}
        {series && (
          <p className="summary-series">{series.title}</p>
        )}
      </div>

      {(effectiveLocation || effectiveLink) && (
        <div className="summary-section">
          {effectiveLink && (
            <a
              href={effectiveLink}
              target="_blank"
              rel="noreferrer"
              className="summary-join-btn"
            >
              Join online meeting
            </a>
          )}
          {effectiveLocation && (
            <div className="summary-location">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="18" height="18">
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/>
                <circle cx="12" cy="10" r="3"/>
              </svg>
              <span>{effectiveLocation}</span>
            </div>
          )}
        </div>
      )}

      {effectiveNotes && (
        <div className="summary-section">
          <h2 className="summary-section-title">Notes</h2>
          <p className="summary-notes">{effectiveNotes}</p>
        </div>
      )}

      <div className="summary-section summary-share">
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={handleCopy}
        >
          {copied ? "Copied!" : "Copy link"}
        </button>
        <Link to={"/occurrences/" + occurrenceId} className="btn btn-secondary btn-sm">
          Organizer view
        </Link>
      </div>

      <div className="summary-footer">
        <span>Powered by Meeting Assistant</span>
      </div>
    </div>
  );
}
