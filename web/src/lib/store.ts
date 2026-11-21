// Zustand — light global store.
// URL is the source of truth for route params. This mirror only holds
// ephemeral cross-page selection + user prefs. Only the fields listed
// in `partialize` survive a page reload.

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { ToastMsg } from '../types/domain';

export type Env = 'LIVE' | 'DEMO';
export type LayoutMode = 'cose' | 'radial' | 'timeline';

interface Actions {
  setSelectedNodeIds: (ids: string[]) => void;
  addSelectedNode: (id: string) => void;
  clearSelection: () => void;
  togglePinnedRing: (id: string) => void;
  setLayout: (l: LayoutMode) => void;
  setEnv: (env: Env) => void;
  setNeo4j: (ok: boolean) => void;
  setCommandPaletteOpen: (open: boolean) => void;
  setShortcutsOpen: (open: boolean) => void;
  pushToast: (t: Omit<ToastMsg, 'id' | 'ts'>) => void;
  dismissToast: (id: string) => void;
  setLatency: (ms: number) => void;
}

interface State {
  selectedNodeIds: string[];
  pinnedRings: string[];
  layout: LayoutMode;
  env: Env;
  neo4jOk: boolean;
  theme: 'dark';
  commandPaletteOpen: boolean;
  shortcutsOpen: boolean;
  toasts: ToastMsg[];
  latencyMs: number;
}

export type AppStore = State & Actions;

let toastCounter = 0;

export const useStore = create<AppStore>()(
  persist(
    (set, get) => ({
      selectedNodeIds: [],
      pinnedRings: [],
      layout: 'cose',
      env: 'LIVE',
      neo4jOk: true,
      theme: 'dark',
      commandPaletteOpen: false,
      shortcutsOpen: false,
      toasts: [],
      latencyMs: 0,

      setSelectedNodeIds: (ids) => set({ selectedNodeIds: ids }),
      addSelectedNode: (id) => set((s) => ({ selectedNodeIds: s.selectedNodeIds.includes(id) ? s.selectedNodeIds : [...s.selectedNodeIds, id] })),
      clearSelection: () => set({ selectedNodeIds: [] }),
      togglePinnedRing: (id) => set((s) => ({ pinnedRings: s.pinnedRings.includes(id) ? s.pinnedRings.filter(x => x !== id) : [...s.pinnedRings, id] })),
      setLayout: (l) => set({ layout: l }),
      setEnv: (env) => set({ env }),
      setNeo4j: (ok) => set({ neo4jOk: ok }),
      setCommandPaletteOpen: (open) => set({ commandPaletteOpen: open }),
      setShortcutsOpen: (open) => set({ shortcutsOpen: open }),
      pushToast: (t) => {
        toastCounter += 1;
        const id = `t-${Date.now()}-${toastCounter}`;
        const msg: ToastMsg = { id, ts: Date.now(), ...t };
        set({ toasts: [...get().toasts, msg] });
        // auto-expire after 6s
        window.setTimeout(() => {
          set({ toasts: get().toasts.filter(x => x.id !== id) });
        }, 6000);
      },
      dismissToast: (id) => set({ toasts: get().toasts.filter(x => x.id !== id) }),
      setLatency: (ms) => set({ latencyMs: ms })
    }),
    {
      name: 'graphgst.selection.v1',
      partialize: (state) => ({
        selectedNodeIds: state.selectedNodeIds,
        pinnedRings: state.pinnedRings,
        layout: state.layout,
        theme: state.theme
      }) as Partial<State>
    }
  )
);
