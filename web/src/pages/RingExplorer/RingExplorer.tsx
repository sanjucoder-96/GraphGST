import { InvestigationPage } from '../Investigation/Investigation';

// Ring explorer is the Investigation page in ring-scoped mode. The route
// is /ring/:ring_id — the same URL used by the ring-focused investigation —
// so this file exists to make the intent explicit at the router level.

export function RingExplorerPage() {
  return <InvestigationPage mode="ring" />;
}
