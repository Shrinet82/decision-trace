import React, { useEffect, useId, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ApiError, deleteOrg } from '../../api/client';
import { useOrgSlug } from '../../org/OrgContext';
import { forgetOrg } from '../../org/orgStore';
import { Drawer } from '../Drawer';
import { btnOutline } from '../ui';

/** Settings for a user organization. Today that is deleting it. */
export const OrgSettingsDrawer: React.FC<{ open: boolean; onClose: () => void; name: string }> = ({
  open,
  onClose,
  name,
}) => {
  const slug = useOrgSlug();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const titleId = useId();

  useEffect(() => {
    if (open) {
      setConfirm(false);
      setBusy(false);
      setError(null);
    }
  }, [open]);

  if (!slug) return null;

  const remove = async () => {
    setBusy(true);
    setError(null);
    try {
      await deleteOrg(slug);
      forgetOrg(slug);
      queryClient.removeQueries({ predicate: (q) => q.queryKey[q.queryKey.length - 1] === slug });
      onClose();
      navigate('/app');
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : 'Could not delete the organization.');
      setBusy(false);
    }
  };

  return (
    <Drawer open={open} onClose={onClose} title="Organization settings" titleId={titleId}>
      <div className="flex flex-col gap-5 p-4">
        <dl className="m-0 grid grid-cols-[96px_1fr] gap-y-2">
          <dt className="text-muted">Name</dt>
          <dd className="m-0">{name}</dd>
          <dt className="text-muted">Id</dt>
          <dd className="m-0 break-all font-mono text-xs">{slug}</dd>
          <dt className="text-muted">Retention</dt>
          <dd className="m-0 text-text-2">Deleted after 72 hours without activity.</dd>
        </dl>
        <section aria-labelledby="danger" className="flex flex-col gap-2 rounded-panel border border-status-conflict-border bg-status-conflict-bg p-3">
          <h3 id="danger" className="m-0 text-sm font-semibold text-status-conflict-text">
            Delete organization
          </h3>
          <p className="m-0 text-text-2">
            Removes the graph and everything in it: decisions, people, systems and the source text. This cannot be undone.
          </p>
          {error && (
            <p role="alert" className="m-0 text-status-conflict-text">
              {error}
            </p>
          )}
          {!confirm ? (
            <button type="button" className={`${btnOutline} h-[30px] self-start`} onClick={() => setConfirm(true)}>
              Delete organization…
            </button>
          ) : (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={remove}
                className="inline-flex h-[30px] items-center rounded-control bg-status-conflict-text px-3 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
              >
                {busy ? 'Deleting…' : `Yes, delete ${name}`}
              </button>
              <button type="button" className={`${btnOutline} h-[30px]`} onClick={() => setConfirm(false)} disabled={busy}>
                Keep it
              </button>
            </div>
          )}
        </section>
      </div>
    </Drawer>
  );
};
