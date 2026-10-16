import React, { useEffect, useId, useRef, useState } from 'react';
import { btnOutline } from './ui';

export interface PopoverButtonProps {
  label: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}

/** Outline button that toggles a small anchored panel; closes on Escape or outside click. */
export const PopoverButton: React.FC<PopoverButtonProps> = ({ label, icon, children }) => {
  const [open, setOpen] = useState(false);
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

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => setOpen((o) => !o)}
        className={btnOutline}
      >
        {icon}
        {label}
      </button>
      {open && (
        <div
          id={panelId}
          role="group"
          aria-label={label}
          className="absolute right-0 top-8 z-20 flex w-56 flex-col gap-3 rounded-panel border border-border bg-surface p-3"
        >
          {children}
        </div>
      )}
    </div>
  );
};
