// Cytoscape stylesheet — SIGNAL edition.
//
// Clean modern nodes on a cool dark canvas. Node TYPE is expressed by
// shape + fill; node RISK/STATE is expressed by border + glow. Electric
// indigo-blue (#4F80FF) is the one interaction accent (selected / hover /
// active-ring / recommended break-edge). Suspicious flow uses the risk
// ramp. Edges render with directional arrows and subtle depth.

type StyleEntry = {
  selector: string;
  style: Record<string, unknown>;
};

export const cyStylesheet: StyleEntry[] = [
  {
    selector: 'node',
    style: {
      'label': 'data(label)',
      'font-family': 'Geist Mono, JetBrains Mono, monospace',
      'font-size': 10,
      'font-weight': 500,
      'color': '#8593A6',
      'text-valign': 'bottom',
      'text-margin-y': 7,
      'text-outline-color': '#070A0F',
      'text-outline-width': 3,
      'background-color': '#161C27',
      'border-color': '#26303F',
      'border-width': 1,
      'overlay-opacity': 0
    }
  },

  {
    // GSTIN — the entity. Rounded card, elevated fill, crisp border.
    selector: 'node[type = "gstin"]',
    style: {
      'shape': 'round-rectangle',
      'width': 34,
      'height': 34,
      'label': 'data(gstin_short)',
      'background-color': '#1A2130',
      'background-gradient-stop-colors': '#1E2632 #141A24',
      'background-gradient-direction': 'to-bottom',
      'border-color': '#35435A',
      'border-width': 1.5,
      'color': '#C2CCDA',
      'font-weight': 600
    }
  },

  {
    // Invoice — a transaction. Small dark node between entities.
    selector: 'node[type = "invoice"]',
    style: {
      'shape': 'ellipse',
      'width': 10,
      'height': 10,
      'label': '',
      'background-color': '#26303F',
      'border-color': '#3BC4E6',
      'border-width': 1,
      'border-opacity': 0.5
    }
  },

  {
    // Ring — the suspicious network. Neutral until opened.
    selector: 'node[type = "ring"]',
    style: {
      'shape': 'round-rectangle',
      'width': 48,
      'height': 48,
      'background-color': 'rgba(79,128,255,0.05)',
      'border-color': '#35435A',
      'border-width': 1.5,
      'border-style': 'dashed',
      'overlay-opacity': 0,
      'label': 'data(label)',
      'font-size': 10,
      'font-weight': 600,
      'color': '#8593A6'
    }
  },
  {
    selector: 'node[type = "ring"].active-ring',
    style: {
      'border-color': '#4F80FF',
      'border-width': 2,
      'border-style': 'solid',
      'overlay-color': '#4F80FF',
      'overlay-opacity': 0.10,
      'overlay-padding': 14,
      'color': '#9CB6FF'
    }
  },

  {
    // Vehicle — logistics satellite.
    selector: 'node[type = "vehicle"]',
    style: {
      'shape': 'round-triangle',
      'width': 12,
      'height': 12,
      'background-color': '#1E2632',
      'border-color': '#4A5568',
      'border-width': 1,
      'label': 'data(label)',
      'font-family': 'Geist Mono, monospace',
      'font-size': 9,
      'color': '#5A6879'
    }
  },

  {
    selector: 'node[type = "taxpayment"]',
    style: {
      'shape': 'round-rectangle',
      'width': 6,
      'height': 14,
      'background-color': '#1E2632',
      'border-color': '#4A5568',
      'border-width': 1
    }
  },

  {
    // Base edge — cool hairline with directional arrow.
    selector: 'edge',
    style: {
      'width': 1.2,
      'line-color': '#26303F',
      'target-arrow-color': '#35435A',
      'target-arrow-shape': 'triangle',
      'arrow-scale': 0.85,
      'curve-style': 'bezier',
      'opacity': 1,
      'label': '',
      'font-family': 'Geist Mono, monospace',
      'font-size': 9,
      'color': '#C2CCDA',
      'text-background-color': '#070A0F',
      'text-background-opacity': 1,
      'text-background-padding': 3,
      'text-background-shape': 'round-rectangle'
    }
  },
  {
    selector: 'edge[amount]',
    style: {
      'width': 'mapData(amount, 0, 3000000, 1.2, 4)',
      'line-color': '#2E3A4C'
    }
  },
  {
    selector: 'edge[kind = "MEMBER"]',
    style: {
      'line-color': '#26303F',
      'target-arrow-color': '#26303F',
      'line-style': 'dashed',
      'width': 1
    }
  },
  {
    selector: 'edge[kind = "CARRIED"]',
    style: {
      'line-color': '#2A2F3A',
      'target-arrow-color': '#2A2F3A',
      'line-style': 'dotted',
      'width': 1
    }
  },

  {
    // Selected node — brand ring + glow.
    selector: 'node:selected',
    style: {
      'border-color': '#4F80FF',
      'border-width': 2,
      'overlay-color': '#4F80FF',
      'overlay-opacity': 0.16,
      'overlay-padding': 7,
      'color': '#F1F5FB'
    }
  },
  {
    selector: 'edge:selected',
    style: {
      'line-color': '#4F80FF',
      'target-arrow-color': '#4F80FF',
      'width': 2.5
    }
  },

  {
    selector: '.hover',
    style: {
      'border-color': '#6E97FF',
      'border-width': 2,
      'label': 'data(gstin_short)',
      'color': '#F1F5FB'
    }
  },
  {
    selector: 'edge.hover',
    style: {
      'line-color': '#4F80FF',
      'target-arrow-color': '#4F80FF',
      'width': 2.5,
      'label': 'data(hoverLabel)'
    }
  },
  {
    // Focus mode — dimmed non-relevant nodes/edges.
    selector: '.dim',
    style: { 'opacity': 0.1 }
  },
  {
    // Counterfactual cut preview — severed edge in red.
    selector: '.cut',
    style: {
      'line-color': '#F24E63',
      'target-arrow-color': '#F24E63',
      'line-style': 'dashed',
      'opacity': 0.4
    }
  },
  {
    // Recommended enforcement edge — brand emphasis.
    selector: '.breakEdge',
    style: {
      'line-color': '#4F80FF',
      'target-arrow-color': '#4F80FF',
      'line-style': 'solid',
      'width': 3,
      'overlay-color': '#4F80FF',
      'overlay-opacity': 0.12,
      'overlay-padding': 3
    }
  }
];
