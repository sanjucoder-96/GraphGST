import { Route, Routes, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppShell } from './components/AppShell/AppShell';
import { CaseQueuePage } from './pages/CaseQueue/CaseQueue';
import { InvestigationPage } from './pages/Investigation/Investigation';
import { RingExplorerPage } from './pages/RingExplorer/RingExplorer';
import { DataHealthPage } from './pages/DataHealth/DataHealth';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false
    }
  }
});

function VendorsRedirect() {
  return <CaseQueuePage />;
}

function DocsPlaceholder() {
  return (
    <div style={{ padding: 24, maxWidth: 720, color: 'var(--text)' }}>
      <h2 style={{ fontSize: 'var(--fs-h)', color: 'var(--text-strong)', fontWeight: 500, marginBottom: 8 }}>Docs</h2>
      <p style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-body)', lineHeight: 1.6 }}>
        Graph GST V6 investigator console. Backend: FastAPI on :8000. Real data flows through
        <span data-mono> /api/rings, /api/vendors, /api/graph/full, /api/reconcile/audit-trail/:id</span>.
        When the backend is unreachable the app falls back to a bundled DEMO fixture so a hackathon
        demo never depends on Neo4j being up.
      </p>
      <ul style={{ marginTop: 16, color: 'var(--text-muted)', fontSize: 'var(--fs-body)', lineHeight: 1.8 }}>
        <li>Case Queue — ranked open alerts (j/k, Enter to open)</li>
        <li>Investigation — Cytoscape + evidence panel with three tabs</li>
        <li>Ring Explorer — timeline scrubber + break simulator</li>
        <li>Data Health — Neo4j + backend status</li>
      </ul>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<CaseQueuePage />} />
          <Route path="/vendors" element={<VendorsRedirect />} />
          <Route path="/rings" element={<Navigate to="/" replace />} />
          <Route path="/entity/:gstin" element={<InvestigationPage mode="entity" />} />
          <Route path="/ring/:ring_id" element={<RingExplorerPage />} />
          <Route path="/data-health" element={<DataHealthPage />} />
          <Route path="/docs" element={<DocsPlaceholder />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </QueryClientProvider>
  );
}
