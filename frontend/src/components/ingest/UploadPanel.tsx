import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { FileText, UploadCloud, X } from 'lucide-react';
import { streamBatch } from '../../api/client';
import { invalidateGraphQueries } from '../../api/hooks';
import type { BatchEvent, BatchFileEvent, BatchPlanFile, IngestDiff, UploadDocType } from '../../api/types';
import {
  ACCEPT,
  DOC_TYPE_LABEL,
  formatBytes,
  MAX_FILES,
  MAX_TOTAL_CHARS,
  readFile,
  selectionProblem,
  toPayload,
  totalChars,
  type PickedFile,
} from '../../utils/uploadFiles';
import { StatusIcon } from '../StatusIcon';
import { btnOutline, btnPrimary } from '../ui';
import { DiffCard } from './DiffCard';
import { useIngest } from './ingestContext';

type Phase = 'pick' | 'running' | 'done' | 'error';

interface FileRow {
  plan: BatchPlanFile;
  status: BatchFileEvent['status'] | 'pending';
  message?: string;
  summary?: string;
  step?: string;
}

const selectClass =
  'h-7 rounded-control border border-border bg-surface px-1.5 text-xs text-text hover:border-[#D5D7DD] focus-visible:border-accent';

/** Upload .md / .txt / .pdf files: pick or drop, choose a type per file, watch each one ingest. */
export const UploadPanel: React.FC = () => {
  const ingest = useIngest();
  const queryClient = useQueryClient();
  const [files, setFiles] = useState<PickedFile[]>([]);
  const [phase, setPhase] = useState<Phase>('pick');
  const [dragging, setDragging] = useState(false);
  const [rows, setRows] = useState<FileRow[]>([]);
  const [diff, setDiff] = useState<IngestDiff | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const setLatestDiff = ingest?.setLatestDiff;

  useEffect(() => () => abortRef.current?.abort(), []);

  const add = useCallback(async (list: FileList | File[]) => {
    const picked = await Promise.all([...list].map(readFile));
    setNotice(null);
    setFiles((current) => {
      const room = MAX_FILES - current.length;
      if (picked.length > room) setNotice(`Only ${MAX_FILES} files per upload: ${picked.length - Math.max(room, 0)} not added.`);
      return [...current, ...picked.slice(0, Math.max(room, 0))];
    });
  }, []);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files.length > 0) void add(e.dataTransfer.files);
  };

  const problem = selectionProblem(files);
  const chars = totalChars(files);

  const apply = (event: BatchEvent) => {
    if (event.event === 'files') {
      setRows(event.data.files.map((plan) => ({ plan, status: plan.rejected ? 'skipped' : 'pending', message: plan.rejected ?? undefined })));
    } else if (event.event === 'file') {
      const e = event.data;
      setRows((rs) => rs.map((r) => (r.plan.index === e.index ? { ...r, status: e.status, message: e.message ?? r.message, summary: e.summary, step: undefined } : r)));
    } else if (event.event === 'step') {
      const { file, label, status } = event.data;
      if (file !== undefined && status === 'running') setRows((rs) => rs.map((r) => (r.plan.index === file ? { ...r, step: label } : r)));
    } else if (event.event === 'diff') {
      setDiff(event.data);
      setLatestDiff?.(event.data);
      void invalidateGraphQueries(queryClient);
    } else if (event.event === 'error') {
      setError(event.data.message);
    }
  };

  const start = async () => {
    if (problem) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setPhase('running');
    setRows([]);
    setDiff(null);
    setError(null);
    let gotDiff = false;
    let gotError = false;
    try {
      await streamBatch(
        toPayload(files),
        (event) => {
          if (controller.signal.aborted) return;
          if (event.event === 'diff') gotDiff = true;
          if (event.event === 'error') gotError = true;
          apply(event);
        },
        controller.signal
      );
      if (controller.signal.aborted) return;
      setPhase(gotDiff ? 'done' : 'error');
      if (!gotDiff && !gotError) setError('The upload finished without a result. Try again.');
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : 'The upload failed.');
      setPhase('error');
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  };

  const cancel = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setPhase('pick');
    setNotice('Upload cancelled. Files already read stay in the graph.');
  };

  const again = () => {
    setFiles([]);
    setRows([]);
    setDiff(null);
    setError(null);
    setNotice(null);
    setPhase('pick');
  };

  if (phase === 'pick') {
    return (
      <div className="flex flex-col gap-3">
        <p className="m-0 text-text-2">
          Upload meeting notes, tickets, ADRs or other documents. Decisions and people are extracted, added to the
          graph, and decision health is recomputed.
        </p>
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          data-testid="dropzone"
          className={`flex flex-col items-center gap-2 rounded-panel border border-dashed px-4 py-6 text-center ${
            dragging ? 'border-accent bg-selected' : 'border-border bg-subtle'
          }`}
        >
          <UploadCloud size={20} aria-hidden="true" className="text-accent" />
          <span className="text-text-2">Drag files here, or</span>
          <button type="button" className={btnOutline} onClick={() => inputRef.current?.click()}>
            Choose files
          </button>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPT}
            aria-label="Choose files to upload"
            className="sr-only"
            onChange={(e) => {
              if (e.target.files) void add(e.target.files);
              e.target.value = '';
            }}
          />
          <span className="text-xs text-muted">
            .md, .txt or .pdf · up to {MAX_FILES} files, 1 MB each, {MAX_TOTAL_CHARS.toLocaleString('en-US')} characters in total
          </span>
        </div>

        {files.length > 0 && (
          <ul aria-label="Files to upload" className="m-0 flex list-none flex-col rounded-panel border border-divider p-0">
            {files.map((f) => (
              <li key={f.id} className="flex flex-wrap items-center gap-2 border-b border-row-divider px-3 py-2 last:border-b-0">
                <FileText size={14} aria-hidden="true" className="shrink-0 text-muted" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{f.name}</span>
                  <span className={`block text-xs ${f.problem ? 'text-status-conflict-text' : 'text-muted'}`}>
                    {f.problem ?? formatBytes(f.size)}
                  </span>
                </span>
                {!f.problem && (
                  <>
                    <label htmlFor={`type-${f.id}`} className="sr-only">
                      Document type for {f.name}
                    </label>
                    <select
                      id={`type-${f.id}`}
                      value={f.type}
                      onChange={(e) => setFiles((fs) => fs.map((x) => (x.id === f.id ? { ...x, type: e.target.value as UploadDocType } : x)))}
                      className={selectClass}
                    >
                      {(Object.keys(DOC_TYPE_LABEL) as UploadDocType[]).map((t) => (
                        <option key={t} value={t}>
                          {DOC_TYPE_LABEL[t]}
                        </option>
                      ))}
                    </select>
                  </>
                )}
                <button
                  type="button"
                  aria-label={`Remove ${f.name}`}
                  onClick={() => setFiles((fs) => fs.filter((x) => x.id !== f.id))}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-control text-muted hover:bg-subtle hover:text-text"
                >
                  <X size={14} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className={btnPrimary} disabled={problem !== null} onClick={() => void start()}>
            {files.filter((f) => !f.problem).length > 1 ? `Ingest ${files.filter((f) => !f.problem).length} files` : 'Ingest file'}
          </button>
          <span className="text-xs text-muted" role="status">
            {files.length > 0 && problem ? problem : files.length > 0 ? `${chars.toLocaleString('en-US')} characters` : 'Choose at least one file.'}
          </span>
        </div>
        {notice && (
          <p role="status" className="m-0 text-xs text-muted">
            {notice}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <section aria-labelledby="upload-files-title" className="flex flex-col rounded-panel border border-divider">
        <div className="flex min-h-9 items-center justify-between gap-2 border-b border-divider px-3">
          <h3 id="upload-files-title" className="m-0 text-sm font-medium">
            Files
          </h3>
          {phase === 'running' && (
            <button type="button" className={btnOutline} onClick={cancel}>
              Cancel
            </button>
          )}
        </div>
        <ol aria-label="Upload progress" className="m-0 flex list-none flex-col p-0">
          {rows.map((r) => (
            <li
              key={r.plan.index}
              data-file-status={r.status}
              className="flex items-start gap-2.5 border-b border-row-divider px-3 py-2 last:border-b-0"
            >
              <span className="mt-[3px] inline-flex shrink-0">
                {r.status === 'done' ? (
                  <StatusIcon status="active" />
                ) : r.status === 'failed' ? (
                  <StatusIcon status="conflict" />
                ) : r.status === 'skipped' ? (
                  <StatusIcon status="superseded" />
                ) : (
                  <span aria-hidden="true" className={`inline-block h-3.5 w-3.5 rounded-full border-2 ${r.status === 'running' ? 'border-accent' : 'border-faint'}`} />
                )}
              </span>
              <span className="flex min-w-0 flex-col">
                <span className={r.status === 'pending' ? 'text-muted' : 'font-medium text-text'}>
                  <span className="sr-only">{r.status}: </span>
                  {r.plan.name}
                  {r.plan.type ? <span className="ml-2 text-xs font-normal text-muted">{DOC_TYPE_LABEL[r.plan.type as UploadDocType] ?? r.plan.type}</span> : null}
                </span>
                {r.status === 'running' && <span className="text-xs text-muted">{r.step ?? 'Starting…'}</span>}
                {r.status === 'done' && r.summary && <span className="text-xs text-muted">{r.summary}</span>}
                {(r.status === 'failed' || r.status === 'skipped') && r.message && (
                  <span className={`break-words text-xs ${r.status === 'failed' ? 'text-status-conflict-text' : 'text-muted'}`}>{r.message}</span>
                )}
              </span>
            </li>
          ))}
          {rows.length === 0 && <li className="px-3 py-2 text-muted">Reading files…</li>}
        </ol>
      </section>

      {phase === 'error' && (
        <div role="alert" className="flex flex-col items-start gap-2 rounded-panel border border-status-conflict-border bg-status-conflict-bg px-3 py-2.5">
          <span className="font-medium text-status-conflict-text">Upload failed</span>
          <span className="text-text-2">{error}</span>
          <button type="button" className={btnOutline} onClick={() => setPhase('pick')}>
            Back to files
          </button>
        </div>
      )}

      {phase === 'done' && diff && (
        <section aria-labelledby="upload-result-title" className="flex flex-col gap-2">
          <h3 id="upload-result-title" className="m-0 text-sm font-medium">
            Result
          </h3>
          <DiffCard diff={diff} onNavigate={ingest?.closeDrawer} />
          <div>
            <button type="button" className={btnOutline} onClick={again}>
              Upload more files
            </button>
          </div>
        </section>
      )}
    </div>
  );
};
