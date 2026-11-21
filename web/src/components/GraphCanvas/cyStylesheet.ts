// Cytoscape stylesheet — MERIDIAN edition.
//
// Instrument-grade graph on a neutral graphite canvas. Node TYPE is expressed
// by shape + fill; interaction (selected / hover / active-ring / recommended
// break-edge) is the ONE place the iris-indigo accent appears. Suspicious flow
// uses the semantic risk ramp. Values mirror styles/tokens.css (MERIDIAN);
// cytoscape needs literal colors, so they are inlined here — keep in sync.

type StyleEntry = {
  selector: string;
  style: Record<string, unknown>;
};

const C = {
  bg0: '#0A0B0E', bg2: '#13151B', bg3: '#191C24', bg4: '#222630',
  line1: '#191D25', line2: '#242A34', line3: '#333B48',
  text0: '#EDF0F5', text1: '#BEC6D2', text2: '#838C9B', text3: '#576070',
  brand: '#6474F0', brand2: '#8492F5', brand3: '#AEB8F9',
  cyan: '#34C2D9', crit: '#EC5064', high: '#E8814A',
};

export const cyStylesheet: StyleEntry[] = [
  {
    selector: 'node',
    style: {
      'label': 'data(label)',
      'font-family': 'Geist Mono, JetBrains Mono, monospace',
      'font-size': 10,
      'font-weight': 500,
      'color': C.text2,
      'text-valign': 'bottom',
      'text-margin-y': 7,
      'text-outline-color': C.bg0,
      'text-outline-width': 3,
      'background-color': C.bg2,
      'border-color': C.line2,
      'border-width': 1,
      'overlay-opacity': 0,
      'transition-property': 'border-color, border-width, background-color',
      'transition-duration': '120ms',
    },
  },

  {
    // GSTIN — the entity. Rounded card, elevated fill, crisp border.
    selector: 'node[type = "gstin"]',
    style: {
      'shape': 'round-rectangle',
      'width': 40,
      'height': 40,
      'label': 'data(gstin_short)',
      'background-color': C.bg3,
      'background-gradient-stop-colors': `${C.bg4} ${C.bg2}`,
      'background-gradient-direction': 'to-bottom',
      'border-color': C.line3,
      'border-width': 1.5,
      'color': C.text1,
      'font-weight': 600,
    },
  },

  {
    // Invoice — a transaction. Small node between entities.
    selector: 'node[type = "invoice"]',
    style: {
      'shape': 'ellipse',
      'width': 11,
      'height': 11,
      'label': '',
      'background-color': C.bg4,
      'border-color': C.cyan,
      'border-width': 1,
      'border-opacity': 0.5,
    },
  },

  {
    // Ring — the suspicious network. Neutral until opened.
    selector: 'node[type = "ring"]',
    style: {
      'shape': 'round-rectangle',
      'width': 54,
      'height': 54,
      'background-color': 'rgba(100,116,240,0.05)',
      'border-color': C.line3,
      'border-width': 1.5,
      'border-style': 'dashed',
      'overlay-opacity': 0,
      'label': 'data(label)',
      'font-size': 10,
      'font-weight': 600,
      'color': C.text2,
    },
  },
  {
    selector: 'node[type = "ring"].active-ring',
    style: {
      'border-color': C.brand,
      'border-width': 2,
      'border-style': 'solid',
      'overlay-color': C.brand,
      'overlay-opacity': 0.10,
      'overlay-padding': 14,
      'color': C.brand3,
    },
  },

  {
    // Vehicle — logistics satellite.
    selector: 'node[type = "vehicle"]',
    style: {
      'shape': 'round-triangle',
      'width': 13,
      'height': 13,
      'background-color': C.bg4,
      'border-color': '#4A5568',
      'border-width': 1,
      'label': 'data(label)',
      'font-family': 'Geist Mono, monospace',
      'font-size': 9,
      'color': C.text3,
    },
  },

  {
    selector: 'node[type = "taxpayment"]',
    style: {
      'shape': 'round-rectangle',
      'width': 6,
      'height': 15,
      'background-color': C.bg4,
      'border-color': '#4A5568',
      'border-width': 1,
    },
  },

  {
    // Base edge — cool hairline with directional arrow.
    selector: 'edge',
    style: {
      'width': 1.2,
      'line-color': C.line2,
      'target-arrow-color': C.line3,
      'target-arrow-shape': 'triangle',
      'arrow-scale': 0.85,
      'curve-style': 'bezier',
      'opacity': 1,
      'label': '',
      'font-family': 'Geist Mono, monospace',
      'font-size': 9,
      'color': C.text1,
      'text-background-color': C.bg0,
      'text-background-opacity': 1,
      'text-background-padding': 3,
      'text-background-shape': 'round-rectangle',
    },
  },
  {
    selector: 'edge[amount]',
    style: {
      'width': 'mapData(amount, 0, 3000000, 1.2, 4)',
      'line-color': '#2E3444',
    },
  },
  {
    selector: 'edge[kind = "MEMBER"]',
    style: {
      'line-color': C.line2,
      'target-arrow-color': C.line2,
      'line-style': 'dashed',
      'width': 1,
    },
  },
  {
    selector: 'edge[kind = "CARRIED"]',
    style: {
      'line-color': '#2A2F3A',
      'target-arrow-color': '#2A2F3A',
      'line-style': 'dotted',
      'width': 1,
    },
  },

  {
    // Selected node — brand ring + glow.
    selector: 'node:selected',
    style: {
      'border-color': C.brand,
      'border-width': 2,
      'overlay-color': C.brand,
      'overlay-opacity': 0.16,
      'overlay-padding': 7,
      'color': C.text0,
    },
  },
  {
    selector: 'edge:selected',
    style: {
      'line-color': C.brand,
      'target-arrow-color': C.brand,
      'width': 2.5,
    },
  },

  {
    selector: '.hover',
    style: {
      'border-color': C.brand2,
      'border-width': 2,
      'label': 'data(gstin_short)',
      'color': C.text0,
    },
  },
  {
    selector: 'edge.hover',
    style: {
      'line-color': C.brand,
      'target-arrow-color': C.brand,
      'width': 2.5,
      'label': 'data(hoverLabel)',
    },
  },
  {
    // Focus mode — dimmed non-relevant nodes/edges.
    selector: '.dim',
    style: { 'opacity': 0.1 },
  },
  {
    // Counterfactual cut preview — severed edge in red.
    selector: '.cut',
    style: {
      'line-color': C.crit,
      'target-arrow-color': C.crit,
      'line-style': 'dashed',
      'opacity': 0.4,
    },
  },
  {
    // Recommended enforcement edge — brand emphasis.
    selector: '.breakEdge',
    style: {
      'line-color': C.brand,
      'target-arrow-color': C.brand,
      'line-style': 'solid',
      'width': 3,
      'overlay-color': C.brand,
      'overlay-opacity': 0.12,
      'overlay-padding': 3,
    },
  },
];
