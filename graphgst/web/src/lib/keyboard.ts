// Global keyboard shortcut hook.
// Registers a keydown listener at window level. Ignores input focus.
// Two-key g-prefix (g q / g r / g v / g h) is time-boxed to 900ms.
//
// Design note: `mapRef` and `armedRef` are both stashed in refs so the effect
// registers exactly one window listener per hook instance — no re-registration
// on caller re-renders, and no reset of the armed g-prefix between key strokes.

import { useEffect, useRef } from 'react';

export type ShortcutHandler = (e: KeyboardEvent) => void;

export interface ShortcutMap {
  [combo: string]: ShortcutHandler;
}

function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (el.isContentEditable) return true;
  return false;
}

function comboFromEvent(e: KeyboardEvent): string {
  const parts: string[] = [];
  if (e.ctrlKey) parts.push('ctrl');
  if (e.metaKey) parts.push('meta');
  if (e.altKey) parts.push('alt');
  if (e.shiftKey) parts.push('shift');
  const k = e.key.toLowerCase();
  parts.push(k);
  return parts.join('+');
}

// Module-level so the armed g-prefix state survives a re-mount of any single
// caller's effect (StrictMode, remounts, sibling re-renders). Only one true
// chord is legal at a time anyway.
let gPrefixArmedAt = 0;

export function useShortcuts(map: ShortcutMap, opts?: { allowInInputs?: boolean }): void {
  const mapRef = useRef<ShortcutMap>(map);
  mapRef.current = map;
  const allowInInputs = opts?.allowInInputs ?? false;

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const currentMap = mapRef.current;
      if (!allowInInputs && isTypingTarget(e.target)) {
        // still allow Escape and command palette
        const isEsc = e.key === 'Escape';
        const isCmdK = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k';
        if (!isEsc && !isCmdK) return;
      }

      const combo = comboFromEvent(e);

      // g-prefix chords — arm on bare 'g'
      if (!e.metaKey && !e.ctrlKey && !e.altKey && !e.shiftKey && e.key === 'g') {
        gPrefixArmedAt = Date.now();
        return;
      }
      if (gPrefixArmedAt && Date.now() - gPrefixArmedAt < 900) {
        const two = `g ${e.key.toLowerCase()}`;
        if (currentMap[two]) {
          e.preventDefault();
          currentMap[two](e);
          gPrefixArmedAt = 0;
          return;
        }
      }
      if (gPrefixArmedAt && Date.now() - gPrefixArmedAt >= 900) gPrefixArmedAt = 0;

      if (currentMap[combo]) {
        e.preventDefault();
        currentMap[combo](e);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [allowInInputs]);
}
