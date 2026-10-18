import type { BatchFilePayload, UploadDocType } from '../api/types';

export const MAX_FILES = 10;
export const MAX_FILE_BYTES = 1_000_000;
export const MAX_TOTAL_CHARS = 50_000;
export const ACCEPT = '.md,.markdown,.txt,.pdf';

export const DOC_TYPE_LABEL: Record<UploadDocType, string> = {
  auto: 'Auto-detect',
  meeting: 'Meeting notes',
  ticket: 'Ticket',
  doc: 'Document',
  adr: 'ADR',
};

export interface PickedFile {
  id: string;
  name: string;
  size: number;
  type: UploadDocType;
  /** Decoded text of a .md or .txt file. */
  text?: string;
  /** A PDF's bytes, base64 encoded. */
  pdfBase64?: string;
  /** Why the file cannot be uploaded; such files are listed but not sent. */
  problem?: string;
}

export function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot === -1 ? '' : name.slice(dot + 1).toLowerCase();
}

export function formatBytes(n: number): string {
  if (n < 1000) return `${n} B`;
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)} KB`;
  return `${(n / 1_000_000).toFixed(1)} MB`;
}

/** The problem with a file judged by name and size alone, or null. */
export function checkFile(name: string, size: number): string | null {
  const ext = extensionOf(name);
  if (!['md', 'markdown', 'txt', 'pdf'].includes(ext)) return 'Only .md, .txt and .pdf files are supported.';
  if (size > MAX_FILE_BYTES) return `Larger than ${formatBytes(MAX_FILE_BYTES)}.`;
  if (size === 0) return 'The file is empty.';
  return null;
}

function toBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  const step = 0x8000;
  for (let i = 0; i < bytes.length; i += step) binary += String.fromCharCode(...bytes.subarray(i, i + step));
  return btoa(binary);
}

function readWith<T extends string | ArrayBuffer>(read: (r: FileReader) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as T);
    reader.onerror = () => reject(reader.error);
    read(reader);
  });
}

let counter = 0;

/** Reads one picked file into a PickedFile (text, or base64 for a PDF). Never throws. */
export async function readFile(file: File): Promise<PickedFile> {
  const base: PickedFile = { id: `f${++counter}`, name: file.name, size: file.size, type: 'auto' };
  const problem = checkFile(file.name, file.size);
  if (problem) return { ...base, problem };
  try {
    if (extensionOf(file.name) === 'pdf') return { ...base, pdfBase64: toBase64(await readWith<ArrayBuffer>((r) => r.readAsArrayBuffer(file))) };
    const text = await readWith<string>((r) => r.readAsText(file));
    if (!text.trim()) return { ...base, problem: 'The file is empty.' };
    return { ...base, text };
  } catch {
    return { ...base, problem: 'The file could not be read.' };
  }
}

/** Characters of text across the files that will be sent (PDF text is only known to the server). */
export function totalChars(files: PickedFile[]): number {
  return files.filter((f) => !f.problem).reduce((n, f) => n + (f.text?.length ?? 0), 0);
}

/** Why the current selection cannot be sent, or null. */
export function selectionProblem(files: PickedFile[]): string | null {
  const usable = files.filter((f) => !f.problem);
  if (usable.length === 0) return 'Add at least one readable file.';
  if (usable.length > MAX_FILES) return `At most ${MAX_FILES} files per upload.`;
  if (totalChars(files) > MAX_TOTAL_CHARS)
    return `Together the files hold more than ${MAX_TOTAL_CHARS.toLocaleString('en-US')} characters. Remove some.`;
  return null;
}

export function toPayload(files: PickedFile[]): BatchFilePayload[] {
  return files
    .filter((f) => !f.problem)
    .map((f) => ({
      name: f.name,
      type: f.type,
      ...(f.pdfBase64 !== undefined ? { pdf_base64: f.pdfBase64 } : { text: f.text }),
    }));
}
