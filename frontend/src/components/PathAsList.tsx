import React from 'react';
import type { GraphPath, Citation } from '../api/types';
import { StatusMarker } from './StatusMarker';
import { getSystemLine } from '../config/lines';

export interface PathAsListProps {
  graphPath: GraphPath | undefined;
  citations?: Citation[];
  onSelectNode?: (nodeId: string, nodeType: string) => void;
}

export const PathAsList: React.FC<PathAsListProps> = ({
  graphPath,
  citations = [],
  onSelectNode,
}) => {
  if (!graphPath || !graphPath.nodes || graphPath.nodes.length === 0) {
    return (
      <div className="p-4 text-sm text-text-muted">
        No graph evidence path available.
      </div>
    );
  }

  const citedIds = new Set(citations.map((c) => c.id));

  // Group nodes by label
  const decisions = graphPath.nodes.filter((n) => n.label === 'Decision');
  const people = graphPath.nodes.filter((n) => n.label === 'Person');
  const systems = graphPath.nodes.filter((n) => n.label === 'System');
  const sources = graphPath.nodes.filter(
    (n) => n.label === 'Ticket' || n.label === 'Meeting'
  );

  return (
    <div
      className="p-4 space-y-6 text-sm"
      role="region"
      aria-label="Evidence path accessible list"
    >
      {/* Decisions section */}
      {decisions.length > 0 && (
        <section aria-labelledby="heading-decisions">
          <h3
            id="heading-decisions"
            className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2"
          >
            Decisions ({decisions.length})
          </h3>
          <ul className="space-y-2 list-none p-0 m-0">
            {decisions.map((node) => {
              const props = node.properties || {};
              const title = (props.title as string) || node.id;
              const status = (props.status as string) || 'active';
              const system = props.system as string | undefined;
              const lineConfig = getSystemLine(system);
              const isCited = citedIds.has(node.id) || citedIds.has(title);

              return (
                <li
                  key={node.id}
                  className={`p-3 rounded-panel border ${
                    isCited
                      ? 'border-primary bg-surface'
                      : 'border-border bg-surface-subtle'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-semibold text-text">{title}</span>
                    <StatusMarker
                      health={status}
                      lineColor={lineConfig.lightColor}
                      showLabel
                    />
                  </div>
                  {Boolean(props.rationale) && (
                    <p className="mt-1 text-xs text-text-muted leading-relaxed">
                      {String(props.rationale)}
                    </p>
                  )}
                  {isCited && (
                    <span className="inline-block mt-2 text-xs font-medium text-primary bg-primary/10 px-2 py-0.5 rounded-control">
                      Direct citation
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {/* Systems section */}
      {systems.length > 0 && (
        <section aria-labelledby="heading-systems">
          <h3
            id="heading-systems"
            className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2"
          >
            Systems ({systems.length})
          </h3>
          <div className="flex flex-wrap gap-2">
            {systems.map((node) => {
              const name = (node.properties?.name as string) || node.id;
              const line = getSystemLine(name);
              return (
                <button
                  type="button"
                  key={node.id}
                  onClick={() => onSelectNode?.(node.id, 'System')}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-control text-xs font-medium border border-border bg-surface text-text hover:border-primary focus-visible:outline-focus"
                >
                  <span
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: line.lightColor }}
                    aria-hidden="true"
                  />
                  <span>{name}</span>
                </button>
              );
            })}
          </div>
        </section>
      )}

      {/* People section */}
      {people.length > 0 && (
        <section aria-labelledby="heading-people">
          <h3
            id="heading-people"
            className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2"
          >
            People ({people.length})
          </h3>
          <div className="flex flex-wrap gap-2">
            {people.map((node) => {
              const name = (node.properties?.name as string) || node.id;
              return (
                <span
                  key={node.id}
                  className="px-2.5 py-1 rounded-control text-xs border border-border bg-surface text-text"
                >
                  {name}
                </span>
              );
            })}
          </div>
        </section>
      )}

      {/* Sources section */}
      {sources.length > 0 && (
        <section aria-labelledby="heading-sources">
          <h3
            id="heading-sources"
            className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2"
          >
            Sources ({sources.length})
          </h3>
          <ul className="space-y-1 list-none p-0 m-0">
            {sources.map((node) => {
              const id = (node.properties?.ticket_id as string) || node.id;
              const title = (node.properties?.title as string) || id;
              return (
                <li
                  key={node.id}
                  className="flex items-center gap-2 text-xs py-1 text-text"
                >
                  <span className="font-mono text-text-muted">{id}:</span>
                  <span>{title}</span>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {/* Relationships / Edges */}
      {graphPath.edges && graphPath.edges.length > 0 && (
        <section aria-labelledby="heading-edges">
          <h3
            id="heading-edges"
            className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2"
          >
            Key connections ({graphPath.edges.length})
          </h3>
          <ul className="space-y-1 list-none p-0 m-0 text-xs text-text-muted">
            {graphPath.edges.map((edge, idx) => {
              let label = edge.type;
              if (edge.type === 'supersedes') label = 'replaces';
              else if (edge.type === 'contradicts') label = 'conflicts with';
              else if (edge.type === 'decided_by') label = 'decided by';
              else if (edge.type === 'based_on') label = 'based on';
              else if (edge.type === 'about_system') label = 'about system';

              return (
                <li key={idx} className="flex items-center gap-1.5">
                  <span className="font-medium text-text">{edge.source}</span>
                  <span className="text-text-muted italic">{label}</span>
                  <span className="font-medium text-text">{edge.target}</span>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
};
