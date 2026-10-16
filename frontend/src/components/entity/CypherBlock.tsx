import React from 'react';
import type { CypherTrace } from '../../api/types';

/** Collapsible "Show Cypher" block: every query that produced the page, with timings. */
export const CypherBlock: React.FC<{ trace: CypherTrace }> = ({ trace }) => (
  <details className="group rounded-panel border border-divider">
    <summary className="flex h-8 cursor-pointer list-none items-center justify-between gap-2 px-3 text-sm font-medium hover:bg-subtle">
      <span>Show Cypher</span>
      <span className="text-xs font-normal text-muted">
        {trace.queries.length} {trace.queries.length === 1 ? 'query' : 'queries'} · {Math.round(trace.total_ms)} ms
      </span>
    </summary>
    <ol className="m-0 flex list-none flex-col gap-3 border-t border-divider p-3">
      {trace.queries.map((q, i) => (
        <li key={`${q.name}-${i}`} className="flex flex-col gap-1">
          <div className="flex items-center justify-between text-xs text-muted">
            <span className="font-medium text-text-2">{q.name}</span>
            <span>{Math.round(q.ms)} ms</span>
          </div>
          <pre className="m-0 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-control bg-subtle p-2 font-mono text-[11px] leading-[1.5] text-text">
            {q.query.replace(/ (OPTIONAL MATCH|MATCH|WHERE|RETURN|UNWIND|ORDER BY|WITH) /g, '\n$1 ')}
          </pre>
          {Object.keys(q.params).length > 0 && (
            <code className="break-words font-mono text-[11px] text-muted">
              params: {JSON.stringify(q.params)}
            </code>
          )}
        </li>
      ))}
    </ol>
  </details>
);
