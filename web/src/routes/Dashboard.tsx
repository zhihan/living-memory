import { useEffect, useState, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  getMe,
  getMyPages,
  createPage,
  type UserProfile,
  type PageSummary,
} from "../api";
import { auth } from "../firebase";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorMessage } from "../components/ErrorMessage";
import { PageCard } from "../components/PageCard";
import { TimezoneSelect } from "../components/TimezoneSelect";

function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function Dashboard() {
  const navigate = useNavigate();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [pages, setPages] = useState<PageSummary[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  // Personal page creation
  const [creatingPersonal, setCreatingPersonal] = useState(false);

  // Create page form
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [formTitle, setFormTitle] = useState("");
  const [formSlug, setFormSlug] = useState("");
  const [formSlugTouched, setFormSlugTouched] = useState(false);
  const [formVisibility, setFormVisibility] = useState<"public" | "personal">(
    "public",
  );
  const [formTimezone, setFormTimezone] = useState(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  );
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [u, p] = await Promise.all([getMe(), getMyPages()]);
      setUser(u);
      setPages(p);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreatePersonalPage() {
    const uid = auth.currentUser?.uid;
    if (!uid) return;
    setCreatingPersonal(true);
    try {
      const slug = `personal-${uid}`;
      await createPage(slug, "Personal Page", "personal");
      navigate(`/p/${slug}`);
    } catch (err) {
      setError(err as Error);
      setCreatingPersonal(false);
    }
  }

  function handleTitleChange(value: string) {
    setFormTitle(value);
    if (!formSlugTouched) {
      setFormSlug(slugify(value));
    }
  }

  async function handleCreatePage(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!formSlug || !formTitle) return;
    setFormSubmitting(true);
    setFormError(null);
    try {
      await createPage(formSlug, formTitle, formVisibility, undefined, formTimezone);
      setShowCreateForm(false);
      setFormTitle("");
      setFormSlug("");
      setFormSlugTouched(false);
      setFormVisibility("public");
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to create page");
    } finally {
      setFormSubmitting(false);
    }
  }

  if (loading) return <LoadingSpinner message="Loading dashboard..." />;
  if (error) return <ErrorMessage error={error} onRetry={load} />;

  return (
    <div className="dashboard">
      <section className="section">
        <h2>Personal Page</h2>
        {user?.default_personal_page_id ? (
          <p>
            <Link to={`/p/${user.default_personal_page_id}`}>
              View your personal page
            </Link>
          </p>
        ) : (
          <p className="placeholder">
            You don't have a personal page yet.{" "}
            <button
              className="btn btn-primary btn-sm"
              onClick={handleCreatePersonalPage}
              disabled={creatingPersonal}
            >
              {creatingPersonal ? "Creating..." : "Create Personal Page"}
            </button>
          </p>
        )}
      </section>

      <section className="section">
        <div className="section-header">
          <h2>My Pages</h2>
          {!showCreateForm && (
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => setShowCreateForm(true)}
            >
              Create Page
            </button>
          )}
        </div>

        {showCreateForm && (
          <form className="create-page-form" onSubmit={handleCreatePage}>
            <div className="form-field">
              <label htmlFor="page-title">Title</label>
              <input
                id="page-title"
                type="text"
                className="form-input"
                value={formTitle}
                onChange={(e) => handleTitleChange(e.target.value)}
                placeholder="My new page"
                required
                disabled={formSubmitting}
              />
            </div>
            <div className="form-field">
              <label htmlFor="page-slug">Slug</label>
              <input
                id="page-slug"
                type="text"
                className="form-input"
                value={formSlug}
                onChange={(e) => {
                  setFormSlug(e.target.value);
                  setFormSlugTouched(true);
                }}
                placeholder="my-new-page"
                required
                disabled={formSubmitting}
              />
            </div>
            <div className="form-field">
              <label>Visibility</label>
              <div className="visibility-toggle">
                <button
                  type="button"
                  className={`btn btn-sm ${formVisibility === "public" ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => setFormVisibility("public")}
                  disabled={formSubmitting}
                >
                  Public
                </button>
                <button
                  type="button"
                  className={`btn btn-sm ${formVisibility === "personal" ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => setFormVisibility("personal")}
                  disabled={formSubmitting}
                >
                  Personal
                </button>
              </div>
            </div>
            <div className="form-field">
              <label htmlFor="page-timezone">Timezone</label>
              <TimezoneSelect
                id="page-timezone"
                value={formTimezone}
                onChange={setFormTimezone}
              />
            </div>
            {formError && <p className="form-error">{formError}</p>}
            <div className="form-actions">
              <button
                type="submit"
                className="btn btn-primary btn-sm"
                disabled={formSubmitting || !formTitle || !formSlug}
              >
                {formSubmitting ? "Creating..." : "Create"}
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  setShowCreateForm(false);
                  setFormError(null);
                }}
                disabled={formSubmitting}
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        {pages && pages.length > 0 ? (
          <ul className="page-list">
            {pages.map((page) => (
              <PageCard key={page.slug} page={page} />
            ))}
          </ul>
        ) : (
          !showCreateForm && <p className="placeholder">No pages yet.</p>
        )}
      </section>
    </div>
  );
}
