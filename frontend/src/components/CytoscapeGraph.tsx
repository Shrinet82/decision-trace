import React, { useEffect, useRef, useState, useCallback } from 'react';
import cytoscape, { Core, EventObject } from 'cytoscape';
import dagre from 'cytoscape-dagre';
import { ZoomIn, ZoomOut, Maximize2, List, Network } from 'lucide-react';
import type { GraphPath, Citation } from '../api/types';
import { convertGraphPathToCytoscape } from '../utils/graphConverter';
import { PathAsList } from './PathAsList';

// Register dagre layout extension
try {
  cytoscape.use(dagre);
} catch {
  // Already registered
}

export interface CytoscapeGraphProps {
  graphPath: GraphPath | undefined;
  citations?: Citation[];
  onSelectNode?: (nodeId: string, nodeType: string, properties: Record<string, unknown>) => void;
  className?: string;
}

export const CytoscapeGraph: React.FC<CytoscapeGraphProps> = ({
  graphPath,
  citations = [],
  onSelectNode,
  className = '',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [viewMode, setViewMode] = useState<'graph' | 'list'>('graph');
  const [selectedNodeData, setSelectedNodeData] = useState<{
    id: string;
    label: string;
    type: string;
    properties: Record<string, unknown>;
  } | null>(null);

  const isDarkMode =
    typeof document !== 'undefined' &&
    (document.documentElement.getAttribute('data-theme') === 'dark' ||
      document.documentElement.classList.contains('dark'));

  const omittedCount = graphPath?.omitted_count || 0;

  // Initialize and update Cytoscape instance
  const initCytoscape = useCallback(() => {
    if (!containerRef.current) return;

    if (cyRef.current) {
      cyRef.current.destroy();
      cyRef.current = null;
    }

    const { elements } = convertGraphPathToCytoscape(
      graphPath,
      citations,
      isDarkMode
    );

    if (elements.nodes.length === 0) return;

    try {
      const cy = cytoscape({
        container: containerRef.current,
      elements,
      boxSelectionEnabled: false,
      autounselectify: false,
      layout: {
        name: 'dagre',
        rankDir: 'LR',
        nodeSep: 45,
        rankSep: 65,
        animate: false,
      } as cytoscape.LayoutOptions,
      style: [
        // Base node
        {
          selector: 'node',
          style: {
            label: 'data(label)',
            'font-family': 'Overpass, sans-serif',
            'font-size': '11px',
            'font-weight': 600,
            color: isDarkMode ? '#E6EDF3' : '#101B26',
            'text-valign': 'center',
            'text-halign': 'center',
            'text-wrap': 'wrap',
            'text-max-width': '90px',
            'background-color': isDarkMode ? '#1E2C3A' : '#EEF1F4',
            'border-width': 1,
            'border-color': isDarkMode ? '#2A3846' : '#D5DBE1',
            padding: '6px',
            width: 'label',
            height: 'label',
          },
        },
        // Decision node (station marker style)
        {
          selector: 'node[nodeType = "decision"]',
          style: {
            shape: 'ellipse',
            width: 32,
            height: 32,
            'background-color': 'data(lineColor)',
            'border-width': 2,
            'border-color': isDarkMode ? '#16212C' : '#FFFFFF',
            label: 'data(label)',
            'text-valign': 'bottom',
            'text-margin-y': 5,
            'font-size': '10px',
            'font-weight': 400,
          },
        },
        // Stale or possibly stale decision node (dashed ring)
        {
          selector: 'node[nodeType = "decision"][health = "possibly_stale"]',
          style: {
            'border-style': 'dashed',
            'border-color': isDarkMode ? '#F5A623' : '#D97706',
            'border-width': 2.5,
          },
        },
        // Cited Decision node (heavier outline)
        {
          selector: 'node[isCited = 1], node[?isCited]',
          style: {
            'border-width': 3,
            'border-color': isDarkMode ? '#4D8BF5' : '#2A68D4',
            'font-weight': 700,
          },
        },
        // Person node
        {
          selector: 'node[nodeType = "person"]',
          style: {
            shape: 'round-rectangle',
            'background-color': isDarkMode ? '#1E2C3A' : '#EEF1F4',
            'border-width': 1,
            'border-color': isDarkMode ? '#2A3846' : '#D5DBE1',
            padding: '4px',
          },
        },
        // System node
        {
          selector: 'node[nodeType = "system"]',
          style: {
            shape: 'round-rectangle',
            'background-color': isDarkMode ? '#16212C' : '#FFFFFF',
            'border-width': 2,
            'border-color': 'data(lineColor)',
            padding: '4px',
          },
        },
        // Ticket node
        {
          selector: 'node[nodeType = "ticket"]',
          style: {
            shape: 'rectangle',
            'font-family': 'Overpass Mono, monospace',
            'font-size': '10px',
            'background-color': isDarkMode ? '#1E2C3A' : '#EEF1F4',
            'border-width': 1,
            'border-color': isDarkMode ? '#2A3846' : '#D5DBE1',
          },
        },
        // Meeting node
        {
          selector: 'node[nodeType = "meeting"]',
          style: {
            shape: 'hexagon',
            'background-color': isDarkMode ? '#1E2C3A' : '#EEF1F4',
            'border-width': 1,
            'border-color': isDarkMode ? '#2A3846' : '#D5DBE1',
          },
        },
        // Selected node highlight
        {
          selector: 'node:selected',
          style: {
            'border-color': isDarkMode ? '#4D8BF5' : '#2A68D4',
            'border-width': 3,
          },
        },
        // Base edge
        {
          selector: 'edge',
          style: {
            width: 1.5,
            label: 'data(label)',
            'font-family': 'Overpass, sans-serif',
            'font-size': '9px',
            color: isDarkMode ? '#9AA9B7' : '#52606D',
            'curve-style': 'taxi',
            'taxi-direction': 'horizontal',
            'target-arrow-shape': 'triangle',
            'target-arrow-color': 'data(edgeColor)',
            'line-color': 'data(edgeColor)',
            'line-style': 'data(edgeStyle)' as cytoscape.Css.LineStyle,
            'text-rotation': 'autorotate',
            'text-margin-y': -6,
          },
        },
        // Supersedes edge (replaces)
        {
          selector: 'edge[type = "supersedes"]',
          style: {
            width: 2,
            'line-style': 'solid',
            'target-arrow-shape': 'triangle',
          },
        },
        // Contradicts edge (conflicts with)
        {
          selector: 'edge[type = "contradicts"]',
          style: {
            width: 2,
            'line-style': 'dashed',
            'line-color': isDarkMode ? '#E55353' : '#C62828',
            'target-arrow-color': isDarkMode ? '#E55353' : '#C62828',
            color: isDarkMode ? '#E55353' : '#C62828',
          },
        },
      ],
    });

    // Handle node click / selection
    cy.on('tap', 'node', (evt: EventObject) => {
      const node = evt.target;
      const data = node.data();
      const nodeInfo = {
        id: data.id,
        label: data.fullTitle || data.label,
        type: data.rawLabel,
        properties: data.properties || {},
      };
      setSelectedNodeData(nodeInfo);
      onSelectNode?.(nodeInfo.id, nodeInfo.type, nodeInfo.properties);
    });

    // Deselect click on background
    cy.on('tap', (evt: EventObject) => {
      if (evt.target === cy) {
        setSelectedNodeData(null);
      }
    });

      cyRef.current = cy;
      cy.fit(undefined, 25);
    } catch {
      // In headless test environments without canvas 2D support, Cytoscape canvas init is safely bypassed
    }
  }, [graphPath, citations, isDarkMode, onSelectNode]);

  useEffect(() => {
    initCytoscape();
    return () => {
      if (cyRef.current) {
        cyRef.current.destroy();
        cyRef.current = null;
      }
    };
  }, [initCytoscape]);

  // When switching back to graph view, resize and fit
  useEffect(() => {
    if (viewMode === 'graph' && cyRef.current) {
      cyRef.current.resize();
      cyRef.current.fit(undefined, 25);
    }
  }, [viewMode]);

  const handleZoomIn = () => {
    if (cyRef.current) {
      cyRef.current.zoom(cyRef.current.zoom() * 1.25);
    }
  };

  const handleZoomOut = () => {
    if (cyRef.current) {
      cyRef.current.zoom(cyRef.current.zoom() * 0.8);
    }
  };

  const handleFit = () => {
    if (cyRef.current) {
      cyRef.current.fit(undefined, 25);
    }
  };

  return (
    <div
      className={`relative flex flex-col h-full bg-surface border border-border rounded-panel overflow-hidden ${className}`}
      role="region"
      aria-label="Evidence path exploration"
    >
      {/* Top toolbar */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-surface-subtle text-xs">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-text">Evidence path</span>
          {omittedCount > 0 && (
            <span
              className="px-2 py-0.5 rounded-control bg-surface border border-border text-text-muted tabular-nums"
              title={`${omittedCount} more evidence nodes were omitted to keep graph legible`}
            >
              {omittedCount} more nodes not shown
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          {/* View toggle (graph vs accessible list) */}
          <button
            type="button"
            onClick={() => setViewMode(viewMode === 'graph' ? 'list' : 'graph')}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-control text-xs font-medium border border-border bg-surface text-text hover:bg-surface-subtle focus-visible:outline-focus"
          >
            {viewMode === 'graph' ? (
              <>
                <List className="w-3.5 h-3.5" aria-hidden="true" />
                <span>Path as list</span>
              </>
            ) : (
              <>
                <Network className="w-3.5 h-3.5" aria-hidden="true" />
                <span>Path as graph</span>
              </>
            )}
          </button>

          {/* Zoom controls only active in graph mode */}
          {viewMode === 'graph' && (
            <div
              className="flex items-center border border-border rounded-control bg-surface overflow-hidden"
              role="group"
              aria-label="Graph zoom and fit controls"
            >
              <button
                type="button"
                onClick={handleZoomIn}
                className="p-1 hover:bg-surface-subtle text-text focus-visible:outline-focus"
                title="Zoom in"
                aria-label="Zoom in"
              >
                <ZoomIn className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={handleZoomOut}
                className="p-1 hover:bg-surface-subtle text-text border-l border-border focus-visible:outline-focus"
                title="Zoom out"
                aria-label="Zoom out"
              >
                <ZoomOut className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={handleFit}
                className="p-1 hover:bg-surface-subtle text-text border-l border-border focus-visible:outline-focus"
                title="Fit to view"
                aria-label="Fit to view"
              >
                <Maximize2 className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Main content body */}
      <div className="relative flex-1 min-h-[380px] w-full">
        <div
          key="graph-canvas-container"
          ref={containerRef}
          className={`w-full h-full min-h-[380px] bg-bg cursor-grab active:cursor-grabbing ${
            viewMode === 'graph' ? 'block' : 'hidden'
          }`}
          tabIndex={0}
          role="application"
          aria-label="Interactive evidence graph. Press Path as list for keyboard-accessible alternative."
        />

        {viewMode === 'list' && (
          <div
            key="accessible-list-container"
            className="w-full h-full overflow-y-auto"
          >
            <PathAsList
              graphPath={graphPath}
              citations={citations}
              onSelectNode={(id, type) =>
                setSelectedNodeData({ id, label: id, type, properties: {} })
              }
            />
          </div>
        )}

        {/* Selected node inspector overlay */}
        {selectedNodeData && viewMode === 'graph' && (
          <div
            className="absolute bottom-3 left-3 right-3 max-w-sm p-3 bg-surface border border-border rounded-panel shadow-md text-xs z-10"
            role="dialog"
            aria-label="Selected node details"
          >
            <div className="flex items-start justify-between gap-2">
              <span className="font-semibold text-text uppercase tracking-wide text-[11px] text-text-muted">
                {selectedNodeData.type}
              </span>
              <button
                type="button"
                onClick={() => setSelectedNodeData(null)}
                className="text-text-muted hover:text-text px-1 focus-visible:outline-focus"
                aria-label="Close node details"
              >
                ✕
              </button>
            </div>
            <div className="mt-1 font-semibold text-text text-sm break-words">
              {selectedNodeData.label}
            </div>
            {Boolean(selectedNodeData.properties.rationale) && (
              <p className="mt-1 text-text-muted leading-relaxed line-clamp-3">
                {String(selectedNodeData.properties.rationale)}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Graph legend */}
      {viewMode === 'graph' && (
        <div className="px-3 py-2 border-t border-border bg-surface text-[11px] text-text-muted flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="font-semibold text-text">Legend:</span>
          <span className="inline-flex items-center gap-1">
            <span
              className="w-2.5 h-2.5 rounded-full inline-block bg-line-platform"
              aria-hidden="true"
            />
            <span>Decision (circle)</span>
          </span>
          <span className="inline-flex items-center gap-1">
            <span
              className="w-2.5 h-2.5 rounded-full inline-block border-2 border-dashed border-warning"
              aria-hidden="true"
            />
            <span>Possibly stale (dashed ring)</span>
          </span>
          <span className="inline-flex items-center gap-1">
            <span
              className="w-3 h-2 rounded-[2px] inline-block bg-surface-subtle border border-border"
              aria-hidden="true"
            />
            <span>Person</span>
          </span>
          <span className="inline-flex items-center gap-1">
            <span
              className="w-3 h-2 rounded-[2px] inline-block bg-surface border border-line-data"
              aria-hidden="true"
            />
            <span>System</span>
          </span>
          <span className="inline-flex items-center gap-1">
            <span
              className="w-3 h-2 inline-block bg-surface-subtle border border-border font-mono text-[9px] text-center"
              aria-hidden="true"
            />
            <span>Ticket</span>
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="inline-block w-4 h-0.5 bg-text-muted" aria-hidden="true" />
            <span>Replaces (solid)</span>
          </span>
          <span className="inline-flex items-center gap-1">
            <span
              className="inline-block w-4 h-0.5 border-t-2 border-dashed border-danger"
              aria-hidden="true"
            />
            <span>Conflicts with (dashed)</span>
          </span>
        </div>
      )}
    </div>
  );
};
