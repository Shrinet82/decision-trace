import React, { useEffect } from 'react';
import { X, FileText, Users, Calendar, Hash } from 'lucide-react';
import type { Citation, GraphPath } from '../api/types';

export interface SourceDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  citation: Citation | null;
  graphPath?: GraphPath;
}

export const SourceDrawer: React.FC<SourceDrawerProps> = ({
  isOpen,
  onClose,
  citation,
  graphPath,
}) => {
  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !citation) {
    return null;
  }

  // Find corresponding node properties in graphPath if available
  const matchingNode = graphPath?.nodes?.find(
    (n) =>
      n.id === citation.id ||
      n.properties?.ticket_id === citation.id ||
      n.properties?.title === citation.title
  );

  const props = matchingNode?.properties || {};
  const date = (props.decided_on as string) || (props.date as string) || (props.created_at as string);

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      role="dialog"
      aria-modal="true"
      aria-labelledby="drawer-title"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/40 transition-opacity duration-150"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer surface */}
      <div className="relative w-full max-w-md h-full bg-surface border-l border-border shadow-2xl flex flex-col z-10 transition-transform duration-150 ease-in-out">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border bg-surface-subtle">
          <div className="flex items-center gap-2">
            {citation.type === 'meeting' ? (
              <Users className="w-4 h-4 text-primary" aria-hidden="true" />
            ) : (
              <FileText className="w-4 h-4 text-primary" aria-hidden="true" />
            )}
            <span className="font-mono text-sm font-semibold text-text">
              {citation.id}
            </span>
            <span className="px-2 py-0.5 rounded-control text-xs font-medium border border-border bg-surface text-text-muted capitalize">
              {citation.type}
            </span>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-control text-text-muted hover:text-text hover:bg-surface border border-transparent hover:border-border transition-colors duration-150 focus-visible:outline-focus"
            aria-label="Close drawer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5 text-sm">
          <div>
            <h2 id="drawer-title" className="text-base font-bold text-text leading-snug">
              {citation.title}
            </h2>
            {date && (
              <div className="flex items-center gap-1.5 mt-2 text-xs text-text-muted tabular-nums">
                <Calendar className="w-3.5 h-3.5" aria-hidden="true" />
                <span>Recorded on {date}</span>
              </div>
            )}
          </div>

          <div className="border-t border-border pt-4 space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
              Source details
            </h3>

            <div className="p-3 bg-surface-subtle border border-border rounded-panel space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-text-muted">Record identifier</span>
                <span className="font-mono text-text font-medium">{citation.id}</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-text-muted">Record type</span>
                <span className="text-text capitalize">{citation.type}</span>
              </div>
              {matchingNode && (
                <div className="flex items-center justify-between text-xs">
                  <span className="text-text-muted">Knowledge graph node</span>
                  <span className="text-text">{matchingNode.label}</span>
                </div>
              )}
            </div>

            {Boolean(props.rationale) && (
              <div>
                <h4 className="text-xs font-semibold text-text-muted mb-1">
                  Recorded rationale
                </h4>
                <p className="text-xs text-text leading-relaxed p-3 bg-surface-subtle border border-border rounded-panel">
                  {String(props.rationale)}
                </p>
              </div>
            )}

            {Boolean(props.status) && (
              <div className="flex items-center gap-2 text-xs">
                <span className="text-text-muted">Status:</span>
                <span className="font-medium text-text capitalize">
                  {String(props.status)}
                </span>
              </div>
            )}
          </div>

          <div className="border-t border-border pt-4">
            <div className="flex items-center gap-2 text-xs text-text-muted">
              <Hash className="w-3.5 h-3.5" aria-hidden="true" />
              <span>Grounded evidence reference in decision graph</span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-border bg-surface-subtle flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-control text-xs font-medium border border-border bg-surface text-text hover:bg-surface-subtle focus-visible:outline-focus"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
