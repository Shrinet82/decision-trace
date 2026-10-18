import React, { useEffect, useId, useRef, useState } from 'react';
import { Link as PlainLink } from 'react-router-dom';
import { Check, ChevronsUpDown, Plus, Settings2 } from 'lucide-react';
import { useShowcaseOrgs } from '../../api/hooks';
import { appBase } from '../../org/orgState';
import { useOrgAccess } from '../../org/useOrgAccess';
import { useOrgSlug } from '../../org/OrgContext';
import { useStoredOrgs } from '../../org/useOrgs';
import { SAMPLE_ORG_NAME } from '../../org/names';
import { NewOrgDrawer } from './NewOrgDrawer';
import { OrgSettingsDrawer } from './OrgSettingsDrawer';

const itemClass =
  'flex h-8 w-full items-center gap-2 rounded-control px-2 text-left text-sm text-text-2 hover:bg-hover';

const Initial: React.FC<{ name: string }> = ({ name }) => (
  <span
    aria-hidden="true"
    className="flex h-5 w-5 shrink-0 items-center justify-center rounded-[5px] bg-accent text-[11px] font-semibold text-white"
  >
    {name.trim().charAt(0).toUpperCase() || '?'}
  </span>
);

/** Top of the sidebar: the current organization and a menu to switch, create or manage one. */
export const OrgSwitcher: React.FC<{ currentName: string }> = ({ currentName }) => {
  const slug = useOrgSlug();
  const stored = useStoredOrgs();
  const showcase = useShowcaseOrgs().data ?? [];
  const { isSample } = useOrgAccess();
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [managing, setManaging] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const others = stored.filter((o) => o.id !== slug);

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => setOpen((o) => !o)}
        className="flex h-9 w-full items-center gap-2 rounded-control border border-border bg-surface px-2 text-left text-sm hover:bg-subtle"
      >
        <Initial name={currentName} />
        <span className="min-w-0 flex-1 truncate font-medium">{currentName}</span>
        <span className="sr-only">, switch organization</span>
        <ChevronsUpDown size={14} aria-hidden="true" className="shrink-0 text-muted" />
      </button>

      {open && (
        <div
          id={panelId}
          role="group"
          aria-label="Organizations"
          className="absolute left-0 right-0 top-10 z-30 flex flex-col gap-px rounded-panel border border-border bg-surface p-1 shadow-composer"
        >
          <PlainLink to="/app" onClick={() => setOpen(false)} className={itemClass} aria-current={!slug ? 'true' : undefined}>
            <Initial name={SAMPLE_ORG_NAME} />
            <span className="flex-1 truncate">{SAMPLE_ORG_NAME}</span>
            {!slug && <Check size={14} aria-hidden="true" className="text-accent" />}
          </PlainLink>
          {showcase.map((o) =>
            o.id === slug ? (
              <PlainLink key={o.id} to={appBase(o.id)} onClick={() => setOpen(false)} className={itemClass} aria-current="true">
                <Initial name={o.name} />
                <span className="flex-1 truncate">{o.name}</span>
                <Check size={14} aria-hidden="true" className="text-accent" />
              </PlainLink>
            ) : (
              <PlainLink key={o.id} to={appBase(o.id)} onClick={() => setOpen(false)} className={itemClass}>
                <Initial name={o.name} />
                <span className="flex-1 truncate">{o.name}</span>
              </PlainLink>
            )
          )}
          {slug && !isSample && (
            <PlainLink to={appBase(slug)} onClick={() => setOpen(false)} className={itemClass} aria-current="true">
              <Initial name={currentName} />
              <span className="flex-1 truncate">{currentName}</span>
              <Check size={14} aria-hidden="true" className="text-accent" />
            </PlainLink>
          )}
          {others.map((o) => (
            <PlainLink key={o.id} to={appBase(o.id)} onClick={() => setOpen(false)} className={itemClass}>
              <Initial name={o.name} />
              <span className="flex-1 truncate">{o.name}</span>
            </PlainLink>
          ))}
          <div role="separator" className="my-1 h-px bg-divider" />
          <button
            type="button"
            className={itemClass}
            onClick={() => {
              setOpen(false);
              setCreating(true);
            }}
          >
            <Plus size={14} aria-hidden="true" />
            New organization
          </button>
          {slug && !isSample && (
            <button
              type="button"
              className={itemClass}
              onClick={() => {
                setOpen(false);
                setManaging(true);
              }}
            >
              <Settings2 size={14} aria-hidden="true" />
              Organization settings
            </button>
          )}
        </div>
      )}

      <NewOrgDrawer open={creating} onClose={() => setCreating(false)} />
      {slug && !isSample && <OrgSettingsDrawer open={managing} onClose={() => setManaging(false)} name={currentName} />}
    </div>
  );
};
