import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search } from 'lucide-react';
import type { DecisionRow } from '../utils/model';
import { askHref } from '../utils/format';
import { StatusIcon } from './StatusIcon';

interface PaletteItem {
  key: string;
  label: string;
  hint: string;
  status?: DecisionRow['status'];
  href: string;
}

export interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  decisions: DecisionRow[];
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({ open, onClose, decisions }) => {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);

  const items = useMemo<PaletteItem[]>(() => {
    const q = query.trim().toLowerCase();
    const matches = decisions
      .filter((d) =>
        q === ''
          ? true
          : [d.title, d.ticketId, d.system, d.decidedBy].some((v) => v?.toLowerCase().includes(q))
      )
      .slice(0, 8)
      .map<PaletteItem>((d) => ({
        key: d.id,
        label: d.title,
        hint: d.ticketId ?? d.system ?? '',
        status: d.status,
        href: `/decisions?selected=${encodeURIComponent(d.id)}`,
      }));
    if (query.trim().length >= 2) {
      matches.push({
        key: 'ask',
        label: `Ask: “${query.trim()}”`,
        hint: 'Ask the Company Brain',
        href: askHref(query.trim()),
      });
    }
    return matches;
  }, [decisions, query]);

  useEffect(() => {
    if (open) {
      setQuery('');
      setActive(0);
      inputRef.current?.focus();
    }
  }, [open]);

  useEffect(() => {
    setActive(0);
  }, [query]);

  if (!open) return null;

  const choose = (item: PaletteItem | undefined) => {
    if (!item) return;
    onClose();
    navigate(item.href);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, items.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      choose(items[active]);
    } else if (e.key === 'Tab') {
      // The input is the only tab stop inside the dialog.
      e.preventDefault();
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-[rgba(16,17,20,0.28)] px-4 pt-[12vh]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search decisions"
        onKeyDown={onKeyDown}
        className="w-full max-w-[560px] overflow-hidden rounded-panel border border-border bg-surface"
      >
        <div className="flex h-11 items-center gap-2 border-b border-divider px-3">
          <Search className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
          <input
            ref={inputRef}
            type="text"
            role="combobox"
            aria-expanded="true"
            aria-controls="palette-results"
            aria-activedescendant={items[active] ? `palette-${items[active].key}` : undefined}
            aria-label="Search decisions or ask a question"
            placeholder="Search decisions or ask a question…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="h-8 flex-1 border-0 bg-transparent text-base text-text outline-none placeholder:text-muted"
          />
        </div>
        <ul
          id="palette-results"
          role="listbox"
          aria-label="Results"
          className="m-0 max-h-[320px] list-none overflow-y-auto p-1"
        >
          {items.length === 0 && (
            <li role="presentation" className="px-3 py-6 text-center text-muted">
              No decisions match.
            </li>
          )}
          {items.map((item, i) => (
            <li
              key={item.key}
              id={`palette-${item.key}`}
              role="option"
              aria-selected={i === active}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(item)}
              className={`flex h-9 cursor-pointer items-center gap-2.5 rounded-control px-3 ${
                i === active ? 'bg-selected' : ''
              }`}
            >
              {item.status ? (
                <StatusIcon status={item.status} />
              ) : (
                <Search className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
              )}
              <span className="min-w-0 flex-1 truncate font-medium">{item.label}</span>
              <span className="shrink-0 text-xs text-muted">{item.hint}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};
