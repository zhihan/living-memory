import { Link } from "react-router-dom";
import type { PageSummary } from "../api";

export function PageCard({ page }: { page: PageSummary }) {
  return (
    <li className="page-card">
      <Link to={`/p/${page.slug}`}>
        <strong>{page.title}</strong>
        <span className={`badge badge-${page.visibility}`}>
          {page.visibility}
        </span>
      </Link>
      {page.description && <p className="page-desc">{page.description}</p>}
      <p className="page-meta-tz">{page.timezone || "UTC"}</p>
    </li>
  );
}
