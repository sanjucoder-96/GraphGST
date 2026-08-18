import { useEffect } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { LeftRail } from '../LeftRail/LeftRail';
import { TopBar } from '../TopBar/TopBar';
import { CommandPalette } from '../CommandPalette/CommandPalette';
import { ShortcutsOverlay } from '../ShortcutsOverlay/ShortcutsOverlay';
import { ToastStack } from '../Toast/Toast';
import { getDashboardSummary, environmentIsDemoNow } from '../../lib/api';
import { useStore } from '../../lib/store';
import { useShortcuts } from '../../lib/keyboard';
import styles from './AppShell.module.css';

export function AppShell() {
  const navigate = useNavigate();
  const setEnv = useStore(s => s.setEnv);
  const setNeo4j = useStore(s => s.setNeo4j);
  const setPaletteOpen = useStore(s => s.setCommandPaletteOpen);
  const setShortcutsOpen = useStore(s => s.setShortcutsOpen);
  const clearSelection = useStore(s => s.clearSelection);
  const setLatency = useStore(s => s.setLatency);
  const latency = useStore(s => s.latencyMs);
  const neo4jOk = useStore(s => s.neo4jOk);
  const env = useStore(s => s.env);

  // Health probe every 20s. Flips env/neo4j based on real response.
  const summary = useQuery({
    queryKey: ['dashboard', 'summary'] as const,
    queryFn: async () => {
      const res = await getDashboardSummary();
      setLatency(res.latency_ms);
      return res;
    },
    refetchInterval: 20_000,
    staleTime: 15_000,
    refetchOnWindowFocus: false
  });

  useEffect(() => {
    if (!summary.data) return;
    const demo = summary.data.fromMock || environmentIsDemoNow();
    setEnv(demo ? 'DEMO' : 'LIVE');
    setNeo4j(!demo && Boolean(summary.data.data.neo4j));
  }, [summary.data, setEnv, setNeo4j]);

  useShortcuts({
    'meta+k':  () => setPaletteOpen(true),
    'ctrl+k':  () => setPaletteOpen(true),
    '/':       () => setPaletteOpen(true),
    'shift+?': () => setShortcutsOpen(true),
    '?':       () => setShortcutsOpen(true),
    'g q':     () => navigate('/'),
    'g r':     () => navigate('/'),
    'g v':     () => navigate('/vendors'),
    'g h':     () => navigate('/data-health'),
    'g m':     () => navigate('/model-card'),
    'escape':  () => { setPaletteOpen(false); setShortcutsOpen(false); clearSelection(); }
  });

  return (
    <div className={styles.shell}>
      <div className={styles.topbar}><TopBar latency={latency} /></div>
      <div className={styles.rail}><LeftRail /></div>
      <main className={styles.main}><Outlet /></main>
      <div className={styles.footer}>
        <div className={styles.footerInner}>
          <span className={neo4jOk ? styles.ok : styles.bad}>{'●'} NEO4J {neo4jOk ? 'OK' : 'OFF'}</span>
          <span className={styles.sep}>│</span>
          <span>LATENCY {latency} ms</span>
          <span className={styles.sep}>│</span>
          <span>ENV {env}</span>
          <span className={styles.sep}>│</span>
          <span>UPDATED {summary.dataUpdatedAt ? new Date(summary.dataUpdatedAt).toISOString().slice(11, 19) : '—'}</span>
        </div>
      </div>
      <CommandPalette />
      <ShortcutsOverlay />
      <ToastStack />
    </div>
  );
}
