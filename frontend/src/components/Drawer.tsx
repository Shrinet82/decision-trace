import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  /** Visible heading; also the dialog's accessible name. */
  title: string;
  titleId: string;
  /** Keep the content mounted while closed so its state (a running ingest) survives. */
  keepMounted?: boolean;
  footer?: React.ReactNode;
  children: React.ReactNode;
}

/**
 * Right-hand modal panel: 480px wide, full width below 640px. Focus moves into the panel when it
 * opens, Tab stays inside it, Escape or a click on the backdrop closes it, and focus returns to
 * the element that opened it.
 */
export const Drawer: React.FC<DrawerProps> = ({
  open,
  onClose,
  title,
  titleId,
  keepMounted = false,
  footer,
  children,
}) => {
  const panelRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !e.defaultPrevented) {
        e.preventDefault();
        onCloseRef.current();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      if (previous && previous.isConnected && previous !== document.body) previous.focus();
      else document.getElementById('main-content')?.focus();
    };
  }, [open]);

  const trapTab = (e: React.KeyboardEvent) => {
    if (e.key !== 'Tab' || !panelRef.current) return;
    const items = [...panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
      (el) => !el.closest('[hidden]')
    );
    if (items.length === 0) {
      e.preventDefault();
      return;
    }
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (e.shiftKey && (active === first || active === panelRef.current)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && active === last) {
      e.preventDefault();
      first.focus();
    }
  };

  if (!open && !keepMounted) return null;

  return (
    <div className="fixed inset-0 z-40" hidden={!open}>
      <div
        aria-hidden="true"
        className="absolute inset-0 bg-[rgba(16,17,20,0.28)]"
        onMouseDown={onClose}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={trapTab}
        className="absolute inset-y-0 right-0 flex w-full flex-col border-l border-border bg-surface outline-none sm:w-[480px]"
      >
        <div className="flex h-11 shrink-0 items-center justify-between gap-2 border-b border-divider px-4">
          <h2 id={titleId} className="m-0 text-sm font-semibold">
            {title}
          </h2>
          <button
            type="button"
            aria-label={`Close ${title.toLowerCase()}`}
            onClick={onClose}
            className="inline-flex h-7 w-7 items-center justify-center rounded-control text-muted transition-colors hover:bg-subtle hover:text-text"
          >
            <X size={15} aria-hidden="true" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
        {footer && <div className="shrink-0 border-t border-divider px-4 py-3">{footer}</div>}
      </div>
    </div>
  );
};
