import React, { useEffect, useRef } from 'react';
import cytoscape, { type Core, type ElementsDefinition } from 'cytoscape';

const FONT = 'Geist, system-ui, sans-serif';

const STYLE = [
  {
    selector: 'node',
    style: {
      shape: 'ellipse',
      width: 'data(size)',
      height: 'data(size)',
      'background-color': 'data(color)',
      'background-opacity': 0.92,
      'border-width': 1.5,
      'border-color': '#FFFFFF',
      label: 'data(label)',
      'font-family': FONT,
      'font-size': 10,
      color: '#1B1C1F',
      'text-valign': 'bottom',
      'text-margin-y': 4,
      'text-wrap': 'none',
      'text-background-color': '#FBFBFC',
      'text-background-opacity': 0.8,
      'text-background-padding': '1.5px',
      'text-background-shape': 'roundrectangle',
      'min-zoomed-font-size': 8,
    },
  },
  { selector: 'node[type = "Decision"]', style: { 'font-weight': 600 } },
  { selector: 'node[type = "Person"][?inactive]', style: { 'background-opacity': 0.45, 'border-style': 'dashed', 'border-color': '#6B6F76' } },
  // Health overlay: only Decision nodes carry a status
  { selector: 'node.health[status = "conflict"]', style: { 'border-width': 3.5, 'border-color': '#D9363E' } },
  { selector: 'node.health[status = "stale"]', style: { 'border-width': 3, 'border-color': '#C77D00', 'border-style': 'dashed' } },
  { selector: 'node.health[status = "superseded"]', style: { 'background-opacity': 0.4, 'border-style': 'dashed', 'border-color': '#9A9DA4', 'border-width': 2 } },
  {
    selector: 'edge',
    style: {
      width: 1,
      'line-color': '#D5D7DD',
      'curve-style': 'haystack',
      'haystack-radius': 0,
      opacity: 0.8,
    },
  },
  { selector: 'edge[type = "supersedes"]', style: { 'line-style': 'dashed', 'line-color': '#9A9DA4', width: 1.5 } },
  { selector: 'edge[type = "contradicts"]', style: { 'line-style': 'dashed', 'line-color': '#D9363E', width: 2 } },
  { selector: '.faded', style: { opacity: 0.12, 'text-opacity': 0 } },
  { selector: 'edge.faded', style: { opacity: 0.05 } },
  { selector: 'node.neighbor', style: { opacity: 1, 'text-opacity': 1 } },
  { selector: 'edge.neighbor', style: { 'line-color': '#4F5BD5', width: 2, opacity: 1 } },
  {
    selector: 'node.sel',
    style: { 'border-color': '#1B1C1F', 'border-width': 3, 'underlay-color': '#E4E6FA', 'underlay-padding': 5, 'underlay-opacity': 1, 'underlay-shape': 'ellipse' },
  },
] as unknown as cytoscape.StylesheetJson;

export interface CompanyMapProps {
  elements: ElementsDefinition;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  healthOverlay: boolean;
  /** Increment to re-fit the viewport. */
  fitSignal: number;
  /** Set to a node id to zoom to it (search). */
  revealId: string | null;
  ariaLabel: string;
}

/**
 * The whole graph as a force-directed map: colour is node type, size is degree, Decision borders
 * show health, clicking a node dims everything but its neighbours. The layout starts from
 * deterministic positions, so the same graph always settles into the same picture.
 */
export const CompanyMap: React.FC<CompanyMapProps> = ({
  elements,
  selectedId,
  onSelect,
  healthOverlay,
  fitSignal,
  revealId,
  ariaLabel,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const onSelectRef = useRef(onSelect);

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
        minZoom: 0.15,
        maxZoom: 3,
      });
    } catch {
      return; // no canvas (jsdom): the node list for screen readers still works
    }
    cy.on('tap', 'node', (evt) => onSelectRef.current(evt.target.id()));
    cy.on('tap', (evt) => {
      if (evt.target === cy) onSelectRef.current(null);
    });
    cyRef.current = cy;
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, []);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.batch(() => {
      cy.elements().remove();
      cy.add(elements);
    });
    if (cy.nodes().length > 0) {
      cy.layout({
        name: 'cose',
        randomize: false,
        animate: false,
        fit: true,
        padding: 40,
        nodeRepulsion: () => 9000,
        idealEdgeLength: () => 60,
        edgeElasticity: () => 80,
        gravity: 0.5,
        numIter: 900,
        nodeDimensionsIncludeLabels: false,
      } as cytoscape.LayoutOptions).run();
      cy.fit(undefined, 40);
    }
  }, [elements]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().toggleClass('health', healthOverlay);
  }, [healthOverlay, elements]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.elements().removeClass('faded neighbor sel');
    if (!selectedId) return;
    const node = cy.getElementById(selectedId);
    if (node.empty()) return;
    const around = node.closedNeighborhood();
    cy.elements().not(around).addClass('faded');
    around.addClass('neighbor');
    node.addClass('sel');
  }, [selectedId, elements]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !revealId) return;
    const node = cy.getElementById(revealId);
    if (node.empty()) return;
    cy.animate({ center: { eles: node }, zoom: Math.max(cy.zoom(), 1.1) }, { duration: 250 });
  }, [revealId]);

  useEffect(() => {
    cyRef.current?.fit(undefined, 40);
  }, [fitSignal]);

  return (
    <div
      ref={containerRef}
      role="img"
      aria-label={ariaLabel}
      data-testid="company-map"
      className="h-full min-h-[420px] w-full bg-panel"
      style={{ backgroundImage: 'radial-gradient(#E3E5E9 1px, transparent 1px)', backgroundSize: '20px 20px' }}
    />
  );
};
