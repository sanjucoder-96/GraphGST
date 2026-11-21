import { Route, Routes, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppShell } from './components/AppShell/AppShell';
import { CaseQueuePage } from './pages/CaseQueue/CaseQueue';
import { InvestigationPage } from './pages/Investigation/Investigation';
import { RingExplorerPage } from './pages/RingExplorer/RingExplorer';
import { DataHealthPage } from './pages/DataHealth/DataHealth';
import { ModelCardPage } from './pages/ModelCard/ModelCard';

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
    <div style={{ padding: '32px 40px', maxWidth: 760, color: 'var(--text-1)' }}>
      <div style={{ fontSize: 'var(--fs-2xs)', fontWeight: 500, color: 'var(--text-3)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 16 }}>Documentation</div>
      <h1 style={{ fontSize: 'var(--fs-2xl)', color: 'var(--text-0)', fontWeight: 600, letterSpacing: '-0.025em', marginBottom: 12 }}>Graph GST intelligence workspace</h1>
      <p style={{ color: 'var(--text-2)', fontSize: 'var(--fs-md)', lineHeight: 1.6 }}>
        Backend: FastAPI on :8000. Live data flows through
        <span data-mono style={{ color: 'var(--text-1)', background: 'var(--bg-3)', padding: '1px 6px', borderRadius: 4, margin: '0 2px' }}>/api/rings</span>,
        <span data-mono style={{ color: 'var(--text-1)', background: 'var(--bg-3)', padding: '1px 6px', borderRadius: 4, margin: '0 2px' }}>/api/vendors</span>,
        <span data-mono style={{ color: 'var(--text-1)', background: 'var(--bg-3)', padding: '1px 6px', borderRadius: 4, margin: '0 2px' }}>/api/graph/full</span>, and
        <span data-mono style={{ color: 'var(--text-1)', background: 'var(--bg-3)', padding: '1px 6px', borderRadius: 4, margin: '0 2px' }}>/api/embed/lookalike</span>.
        When the backend is unreachable the app serves a bundled demo fixture so the workspace never depends on Neo4j being up.
      </p>
      <ul style={{ marginTop: 20, color: 'var(--text-2)', fontSize: 'var(--fs-md)', lineHeight: 2, display: 'flex', flexDirection: 'column', gap: 4 }}>
        <li><strong style={{ color: 'var(--text-1)', fontWeight: 500 }}>Cases</strong> — entities ranked by composed risk (j/k, Enter to open)</li>
        <li><strong style={{ color: 'var(--text-1)', fontWeight: 500 }}>Investigation</strong> — graph canvas + evidence panel with risk decomposition</li>
        <li><strong style={{ color: 'var(--text-1)', fontWeight: 500 }}>Timeline</strong> — transaction-formation replay + break-edge simulator</li>
        <li><strong style={{ color: 'var(--text-1)', fontWeight: 500 }}>Model Card</strong> — benchmark metrics gated against a committed baseline</li>
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
          <Route path="/model-card" element={<ModelCardPage />} />
          <Route path="/docs" element={<DocsPlaceholder />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </QueryClientProvider>
  );
}
