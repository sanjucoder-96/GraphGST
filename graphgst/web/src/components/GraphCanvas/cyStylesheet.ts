// Cytoscape stylesheet.
// GSTIN as squircle, invoice as rounded diamond, ring as glowing circle,
// vehicle as triangle, taxpayment as slim rectangle.
// Selection lifts border to amber + halo. Hover lifts one step.
// Timeline mode uses opacity on edges — driven by TimelineScrubber.
//
// Amber budget: ring nodes are NEUTRAL by default. Only the ring the user has
// picked (marked with class `.active-ring` from the container) gets amber
// border + veil + label. That way a queue with five candidate rings does
// not glow five times before the analyst has chosen one.

// Cytoscape's public types for style entries. Accept any of the exported
// variants so we don't couple to a single @types/cytoscape revision.
type StyleEntry = {
  selector: string;
  style: Record<string, unknown>;
};

export const cyStylesheet: StyleEntry[] = [
  {
    selector: 'node',
    style: {
      'label': 'data(label)',
      'font-family': 'JetBrains Mono, monospace',
      'font-size': 10,
      'color': '#a6adbb',
      'text-valign': 'bottom',
      'text-margin-y': 4,
      'text-outline-color': '#07090c',
      'text-outline-width': 2,
      'background-color': '#12161c',
      'border-color': '#3a4048',
      'border-width': 1,
      'overlay-opacity': 0
    }
  },
  {
    selector: 'node[type = "gstin"]',
    style: {
      'shape': 'round-rectangle',
      'width': 24,
      'height': 24,
      'label': 'data(gstin_short)',
      'background-color': '#12161c',
      'border-color': '#3a4048',
      'border-width': 1
    }
  },
  {
    selector: 'node[type = "invoice"]',
    style: {
      'shape': 'round-diamond',
      'width': 12,
      'height': 12,
      'label': '',
      'background-color': '#1a1d24',
      'border-color': '#5a6068',
      'border-width': 1
    }
  },
  {
    // Ring node — NEUTRAL default. Amber is reserved for `.active-ring` below.
    selector: 'node[type = "ring"]',
    style: {
      'shape': 'ellipse',
      'width': 34,
      'height': 34,
      'background-color': '#0f1319',
      'border-color': '#242a33',
      'border-width': 1,
      'overlay-opacity': 0,
      'label': 'data(label)',
      'font-size': 10,
      'color': '#a6adbb'
    }
  },
  {
    // The one ring the user is currently investigating.
    selector: 'node[type = "ring"].active-ring',
    style: {
      'border-color': '#f2a63a',
      'border-width': 2,
      'overlay-color': '#f2a63a',
      'overlay-opacity': 0.12,
      'overlay-padding': 8,
      'color': '#f2a63a'
    }
  },
  {
    selector: 'node[type = "vehicle"]',
    style: {
      'shape': 'triangle',
      'width': 12,
      'height': 12,
      'background-color': '#2a2d33',
      'border-color': '#4a5058',
      'border-width': 1,
      'label': 'data(label)',
      'font-size': 9,
      'color': '#6e7683'
    }
  },
  {
    selector: 'node[type = "taxpayment"]',
    style: {
      'shape': 'round-rectangle',
      'width': 6,
      'height': 14,
      'background-color': '#1a1d24',
      'border-color': '#4a5058',
      'border-width': 1
    }
  },
  {
    // Base edge — width is a fixed hairline. Edges that carry `amount` map to
    // a proportional width in the next rule, so MEMBER / CARRIED edges never
    // hit `mapData(amount, …)` on an undefined field.
    selector: 'edge',
    style: {
      'width': 1,
      'line-color': '#2a2f36',
      'target-arrow-color': '#2a2f36',
      'target-arrow-shape': 'triangle-backcurve',
      'arrow-scale': 0.8,
      'curve-style': 'bezier',
      'opacity': 1,
      'label': '',
      'font-family': 'JetBrains Mono, monospace',
      'font-size': 9,
      'color': '#a6adbb',
      'text-background-color': '#07090c',
      'text-background-opacity': 1,
      'text-background-padding': 2
    }
  },
  {
    selector: 'edge[amount]',
    style: {
      'width': 'mapData(amount, 0, 3000000, 1, 4)'
    }
  },
  {
    selector: 'edge[kind = "MEMBER"]',
    style: {
      'line-color': '#26303a',
      'target-arrow-color': '#26303a',
      'line-style': 'dashed',
      'width': 1
    }
  },
  {
    selector: 'edge[kind = "CARRIED"]',
    style: {
      'line-color': '#2f2a26',
      'target-arrow-color': '#2f2a26',
      'line-style': 'dotted',
      'width': 1
    }
  },
  {
    selector: 'node:selected',
    style: {
      'border-color': '#f2a63a',
      'border-width': 2,
      'overlay-color': '#f2a63a',
      'overlay-opacity': 0.18,
      'overlay-padding': 6,
      'color': '#f4f6fa'
    }
  },
  {
    selector: 'edge:selected',
    style: {
      'line-color': '#f2a63a',
      'target-arrow-color': '#f2a63a',
      'width': 3
    }
  },
  {
    selector: '.hover',
    style: {
      'border-color': '#f7b95e',
      'border-width': 2,
      'label': 'data(gstin_short)',
      'color': '#f4f6fa'
    }
  },
  {
    selector: 'edge.hover',
    style: {
      'line-color': '#f2a63a',
      'target-arrow-color': '#f2a63a',
      'width': 3,
      'label': 'data(hoverLabel)'
    }
  },
  {
    selector: '.dim',
    style: { 'opacity': 0.15 }
  },
  {
    selector: '.cut',
    style: {
      'line-color': '#c86b5a',
      'target-arrow-color': '#c86b5a',
      'line-style': 'dashed',
      'opacity': 0.35
    }
  },
  {
    selector: '.breakEdge',
    style: {
      'line-color': '#f2a63a',
      'target-arrow-color': '#f2a63a',
      'line-style': 'solid',
      'width': 3
    }
  }
];
