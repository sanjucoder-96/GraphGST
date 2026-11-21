import { useEffect, useMemo, useRef, useState } from 'react';
import cytoscape, { type Core, type ElementDefinition, type EventObject, type LayoutOptions } from 'cytoscape';
import coseBilkent from 'cytoscape-cose-bilkent';
import { Plus, Minus, Maximize2 } from 'lucide-react';
import { useStore, type LayoutMode } from '../../lib/store';
import { cyStylesheet } from './cyStylesheet';
import type { GraphPayload, Ring } from '../../types/domain';
import styles from './GraphCanvas.module.css';

// Register cose-bilkent once
let coseRegistered = false;
function registerCose(): void {
  if (coseRegistered) return;
  try {
    cytoscape.use(coseBilkent as unknown as Parameters<typeof cytoscape.use>[0]);
    coseRegistered = true;
  } catch {
    coseRegistered = true;
  }
}

interface Props {
  data: GraphPayload | null;
  ring?: Ring | null;
  timelineDate?: string | null; // YYYY-MM-DD; when set, edges after this fade
  cutInvoiceId?: string | null;
  onNodeSelect?: (id: string) => void;
  className?: string;
}

interface Tooltip { x: number; y: number; text: string; }
interface ContextMenu { x: number; y: number; nodeId: string | null; edgeId: string | null; }

// Cheap structural fingerprint over the payload — same nodes/edges yield the
// same string even when the array identity changes across a refetch. Used to
// prevent cytoscape from being torn down when the data is materially unchanged.
// Fit the graph to its frame after a layout runs. cose-bilkent's own
// fit:true / layoutstop can land before the flex container reaches its final
// size, leaving the network squeezed into a corner; an explicit fit scheduled
// past the animation is the reliable centring path.
function fitAfterLayout(cy: Core): void {
  requestAnimationFrame(() => { cy.resize(); cy.fit(undefined, 48); });
  setTimeout(() => { cy.resize(); cy.fit(undefined, 48); }, 560);
}

function fingerprint(data: GraphPayload | null): string {
  if (!data) return '';
  let s = '';
  for (const n of data.nodes) s += `n|${n.data.id}|${n.data.type ?? ''}|${n.data.label ?? ''};`;
  for (const e of data.edges) s += `e|${e.data.id ?? ''}|${e.data.source}|${e.data.target}|${e.data.kind ?? ''}|${e.data.amount ?? 0}|${e.data.date ?? ''};`;
  return s;
}

export function GraphCanvas({ data, ring, timelineDate, cutInvoiceId, onNodeSelect, className }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const lastFingerprintRef = useRef<string>('');
  const [tooltip, setTooltip] = useState<Tooltip | null>(null);
  const [menu, setMenu] = useState<ContextMenu | null>(null);
  const [markedIds, setMarkedIds] = useState<Set<string>>(new Set());
  const layout = useStore(s => s.layout);
  const setLayout = useStore(s => s.setLayout);
  const setSelectedNodeIds = useStore(s => s.setSelectedNodeIds);
  const pushToast = useStore(s => s.pushToast);

  // Build elements — memoised on the structural fingerprint so a refetch that
  // returns identical data does not produce a new reference (which would
  // otherwise wipe the layout, selection, zoom and pan).
  const fp = useMemo(() => fingerprint(data), [data]);
  const elements: ElementDefinition[] = useMemo(() => {
    if (!data) return [];
    const els: ElementDefinition[] = [];
    for (const n of data.nodes) {
      els.push({
        group: 'nodes',
        data: {
          ...n.data,
          gstin_short: n.data.gstin_short ?? (n.data.type === 'gstin' ? n.data.id.slice(0, 4) + '…' + n.data.id.slice(-3) : n.data.label)
        }
      });
    }
    for (const e of data.edges) {
      const hoverLabel = e.data.amount !== undefined
        ? `₹${(e.data.amount).toLocaleString('en-IN')} · ${e.data.date ?? ''} · ${e.data.invoice_id ?? ''}`
        : `${e.data.kind ?? ''}`;
      els.push({
        group: 'edges',
        data: { ...e.data, hoverLabel }
      });
    }
    return els;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fp]);

  // Init cytoscape once. Do NOT tear down on element change — instead the
  // effect below diff-swaps elements via cy.json.
  useEffect(() => {
    registerCose();
    if (!canvasRef.current) return;
    if (cyRef.current) return; // already initialised
    const cy = cytoscape({
      container: canvasRef.current,
      elements,
      style: cyStylesheet,
      minZoom: 0.2,
      maxZoom: 3.5,
      wheelSensitivity: 0.25,
      selectionType: 'additive',
      layout: layoutOptionsFor(layout)
    });
    cyRef.current = cy;
    lastFingerprintRef.current = fp;

    cy.on('mouseover', 'node', (evt: EventObject) => {
      const n = evt.target;
      n.addClass('hover');
      const pos = n.renderedPosition();
      const t = n.data('type');
      const label = t === 'gstin'
        ? `${n.data('id')} · ${n.data('label')}`
        : `${n.data('label')} · ${t}`;
      setTooltip({ x: pos.x + 12, y: pos.y - 8, text: label });
    });
    cy.on('mouseout', 'node', (evt: EventObject) => {
      evt.target.removeClass('hover');
      setTooltip(null);
    });
    cy.on('mouseover', 'edge', (evt: EventObject) => {
      const e = evt.target;
      e.addClass('hover');
      const mid = e.midpoint();
      const rendered = cy.pan();
      const zoom = cy.zoom();
      setTooltip({
        x: mid.x * zoom + rendered.x + 12,
        y: mid.y * zoom + rendered.y - 8,
        text: e.data('hoverLabel')
      });
    });
    cy.on('mouseout', 'edge', (evt: EventObject) => {
      evt.target.removeClass('hover');
      setTooltip(null);
    });

    cy.on('select', 'node', () => {
      const ids = cy.$('node:selected').map(n => n.id());
      setSelectedNodeIds(ids);
      onNodeSelect?.(ids[ids.length - 1] ?? '');
    });
    cy.on('unselect', 'node', () => {
      setSelectedNodeIds(cy.$('node:selected').map(n => n.id()));
    });

    cy.on('dbltap', 'node', (evt: EventObject) => {
      const n = evt.target;
      cy.animate({ fit: { eles: n.closedNeighborhood(), padding: 60 } }, { duration: 320, easing: 'ease-in-out' });
      cy.elements().removeClass('dim');
      cy.elements().difference(n.closedNeighborhood()).addClass('dim');
    });

    cy.on('cxttap', 'node', (evt: EventObject) => {
      const rendered = evt.renderedPosition;
      if (!rendered) return;
      setMenu({ x: rendered.x, y: rendered.y, nodeId: evt.target.id(), edgeId: null });
    });
    cy.on('cxttap', 'edge', (evt: EventObject) => {
      const rendered = evt.renderedPosition;
      if (!rendered) return;
      setMenu({ x: rendered.x, y: rendered.y, nodeId: null, edgeId: evt.target.id() });
    });
    cy.on('tap', (evt: EventObject) => {
      if (evt.target === cy) { setMenu(null); }
    });

    // Re-fit whenever the layout settles so the network fills its frame
    // regardless of how big the graph is.
    cy.on('layoutstop', () => { cy.fit(undefined, 48); });

    // Cytoscape can init before the flex container has its final size (the
    // page grid settles a frame later), leaving the graph clustered in a tiny
    // top-left viewport. Observe the container and resize + re-fit on change.
    let raf = 0;
    const ro = new ResizeObserver(() => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        cy.resize();
        cy.fit(undefined, 48);
      });
    });
    if (canvasRef.current) ro.observe(canvasRef.current);
    // The first layout ran while the flex container was still 0-sized, so
    // positions were squeezed into a tiny box. Once the grid settles, resize
    // and RE-RUN the layout (a bare fit would only zoom to the squeezed box).
    const t0 = setTimeout(() => {
      cy.resize();
      cy.layout(layoutOptionsFor(layout, ring)).run();
      fitAfterLayout(cy);
    }, 140);

    return () => {
      ro.disconnect();
      cancelAnimationFrame(raf);
      clearTimeout(t0);
      cy.destroy();
      cyRef.current = null;
      lastFingerprintRef.current = '';
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Diff-swap elements — preserves zoom, pan, selection, and .cut / .breakEdge classes.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    if (fp === lastFingerprintRef.current) return; // identical data — do nothing
    // Preserve selected ids so we can restore them after the swap.
    const preservedSelection = cy.$('node:selected').map(n => n.id());
    cy.batch(() => {
      cy.elements().remove();
      cy.add(elements);
    });
    // Restore selection on ids that still exist.
    for (const id of preservedSelection) {
      const n = cy.getElementById(id);
      if (n && n.nonempty()) n.select();
    }
    // Re-run layout because element positions were dropped.
    cy.layout(layoutOptionsFor(layout, ring)).run();
    fitAfterLayout(cy);
    lastFingerprintRef.current = fp;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fp]);

  // Layout changes
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    const l = cy.layout(layoutOptionsFor(layout, ring));
    l.run();
    fitAfterLayout(cy);
  }, [layout, ring]);

  // Active-ring highlight — repaint amber only on the currently-selected ring node
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes('.active-ring').removeClass('active-ring');
    if (!ring) return;
    const rn = cy.getElementById(ring.ring_id);
    if (rn && rn.nonempty()) rn.addClass('active-ring');
  }, [ring, fp]);

  // Timeline replay: fade edges after the playhead date
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    if (!timelineDate) {
      cy.edges().forEach(e => { e.style('opacity', 1); });
      return;
    }
    const cutoff = new Date(timelineDate).getTime();
    cy.edges().forEach((e) => {
      const d = e.data('date') as string | undefined;
      if (!d) { e.style('opacity', 0.4); return; }
      const t = new Date(d).getTime();
      const visible = t <= cutoff;
      e.style('opacity', visible ? 1 : 0.06);
    });
  }, [timelineDate]);

  // Cut edge visualisation for BreakSimulator preview
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.edges().removeClass('cut');
    if (!cutInvoiceId) return;
    cy.edges().forEach((e) => {
      if (e.data('invoice_id') === cutInvoiceId) e.addClass('cut');
    });
  }, [cutInvoiceId]);

  // Recommended break-edge highlight
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.edges().removeClass('breakEdge');
    if (!ring?.break_edge) return;
    cy.edges().forEach((e) => {
      if (e.data('invoice_id') === ring.break_edge?.invoice_id) e.addClass('breakEdge');
    });
  }, [ring]);

  // Keyboard shortcuts local to canvas.
  // Rules:
  //   - Only fire when focus is inside the canvas container (tabIndex=0 wrap).
  //   - Letter shortcuts require a modifier (Shift) to avoid colliding with
  //     app-level chords like g-h and with typing anywhere else in the app.
  //   - +/- / 0 do not need a modifier: they are already awkward to type by
  //     accident, and only fire when the canvas has focus.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    const handler = (e: KeyboardEvent) => {
      const container = containerRef.current;
      if (!container) return;
      // Focus must be on or inside the canvas container.
      const active = document.activeElement;
      if (active !== container && (!active || !container.contains(active))) return;
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT')) return;
      const k = e.key.toLowerCase();
      if (e.key === '+' || e.key === '=') { e.preventDefault(); cy.zoom({ level: cy.zoom() * 1.2, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } }); }
      else if (e.key === '-' || e.key === '_') { e.preventDefault(); cy.zoom({ level: cy.zoom() / 1.2, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } }); }
      else if (e.key === '0') { e.preventDefault(); cy.fit(undefined, 40); }
      else if (e.shiftKey && k === 'f') { e.preventDefault(); const sel = cy.$('node:selected'); if (sel.nonempty()) cy.animate({ fit: { eles: sel.closedNeighborhood(), padding: 40 } }, { duration: 320 }); }
      else if (e.shiftKey && k === 'e') { e.preventDefault(); expandNeighbors(cy); }
      else if (e.shiftKey && k === 'i') { e.preventDefault(); isolate(cy); }
      else if (e.shiftKey && k === 'h') { e.preventDefault(); hideSelection(cy); }
      else if (e.shiftKey && k === 'm') { e.preventDefault(); const sel = cy.$(':selected'); const ids = new Set(markedIds); sel.forEach((el) => { ids.add(el.id()); }); setMarkedIds(ids); pushToast({ kind: 'info', title: `Marked ${sel.length} for report` }); }
      else if ((e.metaKey || e.ctrlKey) && k === 'c') { const sel = cy.$(':selected'); if (sel.length === 1) { navigator.clipboard.writeText(sel.id()).catch(() => {}); pushToast({ kind: 'ok', title: 'Copied id', body: sel.id() }); } }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [markedIds, pushToast]);

  const layouts: { key: LayoutMode; label: string }[] = [
    { key: 'cose',    label: 'Cose' },
    { key: 'radial',  label: 'Radial' },
    { key: 'timeline',label: 'Timeline' }
  ];

  return (
    <div
      className={`${styles.wrap} ${className ?? ''}`}
      ref={containerRef}
      tabIndex={0}
      aria-label="Graph canvas"
    >
      <div className={styles.canvas} ref={canvasRef} />
      <div className={styles.overlay}>
        <div className={styles.layouts}>
          {layouts.map((l) => (
            <button
              key={l.key}
              type="button"
              className={l.key === layout ? styles.active : ''}
              onClick={() => setLayout(l.key)}
            >
              {l.label}
            </button>
          ))}
        </div>
        <div className={styles.spacer} />
        <div className={styles.legend}>
          <span><span className={styles.sq} /> GSTIN</span>
          <span><span className={styles.di} /> Invoice</span>
          <span><span className={styles.rg} /> Ring</span>
          <span><span className={styles.tr} /> Vehicle</span>
        </div>
        <div className={styles.zoom}>
          <button type="button" onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 1.2)} title="Zoom in (+)"><Plus size={12} strokeWidth={1.5} /></button>
          <button type="button" onClick={() => cyRef.current?.zoom(cyRef.current.zoom() / 1.2)} title="Zoom out (-)"><Minus size={12} strokeWidth={1.5} /></button>
          <button type="button" onClick={() => cyRef.current?.fit(undefined, 40)} title="Fit (0)"><Maximize2 size={12} strokeWidth={1.5} /></button>
        </div>
      </div>
      {tooltip && (
        <div className={styles.tooltip} style={{ left: tooltip.x, top: tooltip.y }} data-mono>
          {tooltip.text}
        </div>
      )}
      {menu && (
        <div className={styles.ctxMenu} style={{ left: menu.x, top: menu.y }} onClick={() => setMenu(null)}>
          {menu.nodeId && (
            <>
              <div className={styles.ctxItem} onClick={() => { expandNeighbors(cyRef.current!); }}>Expand neighbors <span className={styles.k}>⇧E</span></div>
              <div className={styles.ctxItem} onClick={() => { isolate(cyRef.current!); }}>Isolate subgraph <span className={styles.k}>⇧I</span></div>
              <div className={styles.ctxItem} onClick={() => { hideSelection(cyRef.current!); }}>Hide node <span className={styles.k}>⇧H</span></div>
              <div className={styles.ctxItem} onClick={() => { const ids = new Set(markedIds); ids.add(menu.nodeId!); setMarkedIds(ids); pushToast({ kind: 'info', title: 'Marked for report', body: menu.nodeId! }); }}>Mark for report <span className={styles.k}>⇧M</span></div>
              <div className={styles.ctxDivider} />
              <div className={styles.ctxItem} onClick={() => { navigator.clipboard.writeText(menu.nodeId!).catch(() => {}); pushToast({ kind: 'ok', title: 'Copied id', body: menu.nodeId! }); }}>Copy id <span className={styles.k}>⌘C</span></div>
              <div className={styles.ctxItem} onClick={() => { pushToast({ kind: 'info', title: 'Opened in evidence', body: menu.nodeId! }); onNodeSelect?.(menu.nodeId!); }}>View in evidence <span className={styles.k}>↵</span></div>
            </>
          )}
          {menu.edgeId && (
            <>
              <div className={styles.ctxItem} onClick={() => { navigator.clipboard.writeText(menu.edgeId!).catch(() => {}); pushToast({ kind: 'ok', title: 'Copied edge id', body: menu.edgeId! }); }}>Copy edge id <span className={styles.k}>⌘C</span></div>
              <div className={styles.ctxItem} onClick={() => { pushToast({ kind: 'info', title: 'Would open audit trail', body: menu.edgeId! }); }}>Open audit trail <span className={styles.k}>A</span></div>
            </>
          )}
        </div>
      )}
      {(!data || data.nodes.length === 0) && (
        <div className={styles.empty}>
          <div className={styles.emptyBox}>Select an entity or ring from the queue.</div>
        </div>
      )}
    </div>
  );
}

function layoutOptionsFor(mode: LayoutMode, ring?: Ring | null): LayoutOptions {
  if (mode === 'radial') {
    return {
      name: 'concentric',
      concentric: (node: cytoscape.NodeSingular) => (node.data('type') === 'ring' ? 3 : node.data('type') === 'gstin' ? 2 : 1),
      levelWidth: () => 1,
      minNodeSpacing: 44,
      startAngle: -Math.PI / 2,
      animate: false,
      fit: true,
      padding: 56,
      spacingFactor: 1
    } as unknown as LayoutOptions;
  }
  if (mode === 'timeline') {
    // preset positions based on invoice date; nodes without date get bucketed by type
    return {
      name: 'preset',
      positions: ((node: cytoscape.NodeSingular) => positionByTimeline(node, ring)) as unknown as Record<string, cytoscape.Position>,
      fit: true,
      padding: 40,
      animate: false
    } as unknown as LayoutOptions;
  }
  return {
    name: 'cose-bilkent',
    idealEdgeLength: 95,
    nodeRepulsion: 9000,
    nodeOverlap: 24,
    numIter: 1200,
    animate: false,
    randomize: true,
    fit: true,
    padding: 56,
    tile: false,
    edgeElasticity: 0.45
  } as unknown as LayoutOptions;
}

function positionByTimeline(node: cytoscape.NodeSingular, ring?: Ring | null): cytoscape.Position {
  const t = (node.data('type') as string) ?? '';
  const yBucket: Record<string, number> = { gstin: 0, invoice: 120, ring: -120, vehicle: 240, taxpayment: 360 };
  const dates: number[] = [];
  if (ring) for (const e of ring.edges) dates.push(new Date(e.date).getTime());
  const min = dates.length ? Math.min(...dates) : 0;
  const max = dates.length ? Math.max(...dates) : 1;
  const span = Math.max(1, max - min);
  const width = 900;
  if (t === 'invoice') {
    const own = ring?.edges.find(e => e.invoice_id === node.data('id'));
    const at = own ? new Date(own.date).getTime() : min;
    const x = ((at - min) / span) * width;
    return { x, y: yBucket[t] };
  }
  const id = node.data('id') as string;
  const hash = [...id].reduce((s, c) => s + c.charCodeAt(0), 0);
  const x = (hash % 900);
  return { x, y: yBucket[t] ?? 0 };
}

function expandNeighbors(cy: Core): void {
  const sel = cy.$(':selected');
  if (sel.empty()) return;
  cy.elements().removeClass('dim');
  const neigh = sel.closedNeighborhood();
  cy.elements().difference(neigh).addClass('dim');
}

function isolate(cy: Core): void {
  const sel = cy.$(':selected');
  if (sel.empty()) return;
  const neigh = sel.closedNeighborhood();
  cy.elements().difference(neigh).addClass('dim');
}

function hideSelection(cy: Core): void {
  const sel = cy.$(':selected');
  if (sel.empty()) return;
  sel.style('display', 'none');
  sel.unselect();
}
