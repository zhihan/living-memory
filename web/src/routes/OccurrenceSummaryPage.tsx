import { useEffect, useState, useCallback } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  getPublicOccurrenceSummary,
  type PublicOccurrenceSummary,
} from "../api";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorMessage } from "../components/ErrorMessage";
import { formatDate } from "../dateFormat";
import { QRCodeSVG } from "qrcode.react";

export function OccurrenceSummaryPage() {
  const { occurrenceId } = useParams<{ occurrenceId: string }>();
  const [searchParams] = useSearchParams();
  const inviteId = searchParams.get("invite");

  const [summary, setSummary] = useState<PublicOccurrenceSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    if (!occurrenceId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getPublicOccurrenceSummary(occurrenceId);
      setSummary(data);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [occurrenceId]);

  useEffect(() => { load(); }, [load]);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.warn("Clipboard write failed:", err);
    }
  }

  if (loading) return <LoadingSpinner message="Loading meeting details..." />;
  if (error) return <ErrorMessage error={error} onRetry={load} />;

  const occ = summary!;
  const effectiveTitle = occ.overrides?.title ?? occ.series_title ?? "Meeting";
  const effectiveLocation = occ.location ?? occ.overrides?.location ?? occ.default_location;
  const effectiveLink = occ.overrides?.online_link ?? occ.default_online_link;
  const effectiveNotes = occ.overrides?.notes;
  const effectiveDuration = occ.overrides?.duration_minutes ?? occ.default_duration_minutes;

  const isCancelled = occ.status === "cancelled" || occ.status === "skipped";

  const inviteUrl = inviteId
    ? `${window.location.origin}/invites/${inviteId}`
    : null;

  return (
    <div className="summary-page">
      {isCancelled && (
        <div className="summary-cancelled-banner">
          This meeting has been {occ.status}.
        </div>
      )}

      <div className="summary-hero">
        <h1 className="summary-title">{effectiveTitle}</h1>
        <p className="summary-date">{formatDate(occ.scheduled_for, undefined, { weekday: "long", year: "numeric", month: "long", day: "numeric", hour: "numeric", minute: "2-digit" })}</p>
        {effectiveDuration && (
          <p className="summary-duration">{effectiveDuration} minutes</p>
        )}
        <p className="summary-series">{occ.series_title}</p>
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

      {inviteUrl && (
        <div className="summary-section summary-invite">
          <h2 className="summary-section-title">Join this group</h2>
          <div className="summary-qr">
            <QRCodeSVG value={inviteUrl} size={160} />
          </div>
          <a href={inviteUrl} className="btn btn-primary btn-sm">
            Join this group
          </a>
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
        <span>Powered by Small Group</span>
      </div>
    </div>
  );
}
