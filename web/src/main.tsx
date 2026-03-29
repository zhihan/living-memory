import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider, RequireAuth } from "./auth";
import { AppShell } from "./components/AppShell";
import { Landing } from "./routes/Landing";
import { SignIn } from "./routes/SignIn";
import { WorkspaceDashboard } from "./routes/WorkspaceDashboard";
import { WorkspaceView } from "./routes/WorkspaceView";
import { SeriesView } from "./routes/SeriesView";
import { OccurrenceView } from "./routes/OccurrenceView";
import { OccurrenceSummaryPage } from "./routes/OccurrenceSummaryPage";
// Legacy routes kept for compatibility during migration
import { Dashboard } from "./routes/Dashboard";
import { PageView } from "./routes/PageView";
import { PageSettings } from "./routes/PageSettings";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/sign-in" element={<SignIn />} />

          {/* Participant-facing public summary — no auth required */}
          <Route path="/occurrences/:occurrenceId/summary" element={<OccurrenceSummaryPage />} />

          <Route element={<AppShell />}>
            {/* New workspace-centric routes */}
            <Route
              path="/dashboard"
              element={
                <RequireAuth>
                  <WorkspaceDashboard />
                </RequireAuth>
              }
            />
            <Route
              path="/w/:workspaceId"
              element={
                <RequireAuth>
                  <WorkspaceView />
                </RequireAuth>
              }
            />
            <Route
              path="/w/:workspaceId/series/:seriesId"
              element={
                <RequireAuth>
                  <SeriesView />
                </RequireAuth>
              }
            />
            <Route
              path="/occurrences/:occurrenceId"
              element={
                <RequireAuth>
                  <OccurrenceView />
                </RequireAuth>
              }
            />

            {/* Legacy page routes — kept during migration */}
            <Route
              path="/pages"
              element={
                <RequireAuth>
                  <Dashboard />
                </RequireAuth>
              }
            />
            <Route
              path="/p/:slug"
              element={
                <RequireAuth>
                  <PageView />
                </RequireAuth>
              }
            />
            <Route
              path="/p/:slug/settings"
              element={
                <RequireAuth>
                  <PageSettings />
                </RequireAuth>
              }
            />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
