import React, { useEffect, useRef, useState } from 'react';
import cytoscape, { type Core, type ElementsDefinition } from 'cytoscape';
const FONT = 'Geist, system-ui, sans-serif';

// Cast: the bundled typings lag behind Cytoscape 3.34 style properties (corner-radius, underlay-*).
const STYLE = [
  {
    selector: 'node',
    style: {
      shape: 'round-rectangle',
      'background-color': '#FFFFFF',
      'border-width': 1,
      'border-color': '#E6E7EB',
      width: 'label',
      height: 32,
      padding: '16px',
      label: 'data(label)',
      'font-family': FONT,
      'font-size': 12,
      color: '#1B1C1F',
      'text-valign': 'center',
      'text-halign': 'center',
      'text-margin-x': 9,
      'background-image': 'data(icon)',
      'background-width': 14,
      'background-height': 14,
      'background-position-x': 10,
      'background-position-y': '50%',
      'background-fit': 'none',
      'background-repeat': 'no-repeat',
      'background-clip': 'none',
    },
  },
  {
    selector: 'node[type = "Decision"]',
    style: { 'font-weight': 600 },
  },
  {
    selector: 'node[type = "Person"]',
    style: { 'corner-radius': 16, 'background-width': 20, 'background-height': 20, 'background-position-x': 6, 'text-margin-x': 11 },
  },
  {
    selector: 'node[type = "Person"][?inactive]',
    style: { 'border-style': 'dashed', 'border-color': '#C9CCD3', color: '#6B6F76' },
  },
  {
    selector: 'node[status = "superseded"][type = "Decision"]',
    style: { color: '#6B6F76' },
  },
  {
    selector: 'node.sel',
    style: {
      'border-color': '#4F5BD5',
      'border-width': 1.5,
      'underlay-color': '#E4E6FA',
      'underlay-padding': 3,
      'underlay-opacity': 1,
      'underlay-shape': 'round-rectangle',
    },
  },
  {
    selector: 'edge',
    style: {
      width: 1.5,
      'line-color': '#C9CCD3',
      'curve-style': 'bezier',
      'target-arrow-shape': 'none',
      label: 'data(label)',
      'font-family': FONT,
      'font-size': 11,
      color: '#6B6F76',
      'text-background-color': '#FFFFFF',
      'text-background-opacity': 1,
      'text-background-padding': '3px',
      'text-background-shape': 'roundrectangle',
      'text-border-width': 1,
      'text-border-color': '#EDEEF1',
      'text-border-opacity': 1,
    },
  },
  {
    selector: 'edge[type = "supersedes"]',
    style: { 'line-style': 'dashed', 'line-color': '#9A9DA4', 'line-dash-pattern': [5, 4] },
  },
  {
    selector: 'edge[type = "contradicts"]',
    style: { 'line-style': 'dashed', 'line-color': '#D9363E', 'line-dash-pattern': [5, 4] },
  },
] as unknown as cytoscape.StylesheetJson;

function useFontsReady(): boolean {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    let cancelled = false;
    const done = () => {
      if (!cancelled) setReady(true);
    };
    const fonts = typeof document !== 'undefined' ? document.fonts : undefined;
    if (!fonts) {
      done();
    } else {
      // Label widths depend on the font, so wait for it (but never block for long).
      Promise.race([
        Promise.all([fonts.load('12px Geist'), fonts.load('600 12px Geist')]).then(() => fonts.ready),
        new Promise((resolve) => setTimeout(resolve, 1500)),
      ]).then(done, done);
    }
    return () => {
      cancelled = true;
    };
  }, []);
  return ready;
}

export interface CytoscapeGraphProps {
  elements: ElementsDefinition;
  /** Node the radial layout is centred on. */
  focusId: string | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  /** Increment to re-fit the viewport. */
  fitSignal: number;
  ariaLabel: string;
}

export const CytoscapeGraph: React.FC<CytoscapeGraphProps> = ({
  elements,
  focusId,
  selectedId,
  onSelect,
  fitSignal,
  ariaLabel,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const onSelectRef = useRef(onSelect);
  const fontsReady = useFontsReady();

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    if (!containerRef.current) return;
    let cy: Core;
    try {
      cy = cytoscape({
        container: containerRef.current,
        style: STYLE,
        boxSelectionEnabled: false,
        autounselectify: true,
        wheelSensitivity: 0.25,
        minZoom: 0.2,
        maxZoom: 2.5,
      });
    } catch {
      // No canvas support (e.g. jsdom): the sr-only node list still works.
      return;
    }
    cy.on('tap', 'node', (evt) => onSelectRef.current(evt.target.id()));
    cyRef.current = cy;
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, []);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !fontsReady) return;
    cy.batch(() => {
      cy.elements().remove();
      cy.add(elements);
    });
    const narrow = (containerRef.current?.clientWidth ?? 1000) < 600;
    // Radial: the focus node in the middle, each hop on its own ring.
    cy.layout({
      name: 'breadthfirst',
      roots: focusId ? cy.getElementById(focusId) : undefined,
      circle: true,
      directed: false,
      spacingFactor: narrow ? 0.8 : 1.15,
      avoidOverlap: true,
      nodeDimensionsIncludeLabels: true,
      padding: 30,
      animate: false,
    } as cytoscape.LayoutOptions).run();
    cy.fit(undefined, 40);
    // Keep labels legible: never zoom out past a floor (pan to see the rest) or in past 1.2.
    const floor = narrow ? 0.62 : 0.45;
    if (cy.zoom() < floor) {
      cy.zoom(floor);
      cy.center(focusId ? cy.getElementById(focusId) : undefined);
    } else if (cy.zoom() > 1.2) {
      cy.zoom(1.2);
      cy.center();
    }
  }, [elements, focusId, fontsReady]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().removeClass('sel');
    if (selectedId) cy.getElementById(selectedId).addClass('sel');
  }, [selectedId, elements, fontsReady]);

  useEffect(() => {
    cyRef.current?.fit(undefined, 40);
  }, [fitSignal]);

  return (
    <div
      ref={containerRef}
      role="img"
      aria-label={ariaLabel}
      data-testid="graph-canvas"
      className="h-full min-h-[420px] w-full bg-panel"
      style={{
        backgroundImage: 'radial-gradient(#E3E5E9 1px, transparent 1px)',
        backgroundSize: '20px 20px',
      }}
    />
  );
};
