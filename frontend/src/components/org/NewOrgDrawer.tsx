import React, { useEffect, useId, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError, createOrg } from '../../api/client';
import { appBase } from '../../org/orgState';
import { rememberOrg } from '../../org/orgStore';
import { Drawer } from '../Drawer';
import { btnOutline, btnPrimary } from '../ui';

const MAX_NAME = 40;

/** Name an organization and create it; lands on its (empty) Home. */
export const NewOrgDrawer: React.FC<{ open: boolean; onClose: () => void }> = ({ open, onClose }) => {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const titleId = useId();
  const inputId = useId();

  useEffect(() => {
    if (open) {
      setName('');
      setError(null);
      setBusy(false);
    }
  }, [open]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError('Give the organization a name.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const org = await createOrg(trimmed);
      rememberOrg(org, org.owner_key);
      onClose();
      navigate(appBase(org.id));
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : 'Could not create the organization.');
      setBusy(false);
    }
  };

  return (
    <Drawer open={open} onClose={onClose} title="New organization" titleId={titleId}>
      <form onSubmit={submit} className="flex flex-col gap-4 p-4">
        <p className="m-0 text-text-2">
          An organization is its own brain: a separate graph in FalkorDB that starts empty. Add sources to it by
          uploading files or importing a GitHub repository.
        </p>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={inputId} className="text-xs font-medium text-muted">
            Name
          </label>
          <input
            id={inputId}
            value={name}
            maxLength={MAX_NAME}
            onChange={(e) => setName(e.target.value)}
            placeholder="Acme Labs"
            autoComplete="off"
            className="h-[30px] rounded-control border border-border bg-surface px-2 text-sm text-text outline-none placeholder:text-muted focus:border-accent focus:shadow-[0_0_0_3px_var(--color-accent-ring)]"
          />
          <span className="text-xs text-muted">Up to {MAX_NAME} characters. Unused organizations are deleted after 72 hours.</span>
        </div>
        {error && (
          <p role="alert" className="m-0 rounded-control border border-status-conflict-border bg-status-conflict-bg px-3 py-2 text-status-conflict-text">
            {error}
          </p>
        )}
        <div className="flex gap-2">
          <button type="submit" className={btnPrimary} disabled={busy}>
            {busy ? 'Creating…' : 'Create organization'}
          </button>
          <button type="button" className={`${btnOutline} h-[30px]`} onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Drawer>
  );
};
