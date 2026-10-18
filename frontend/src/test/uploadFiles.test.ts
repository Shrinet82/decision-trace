import { describe, expect, it } from 'vitest';
import {
  checkFile,
  extensionOf,
  formatBytes,
  MAX_FILE_BYTES,
  MAX_FILES,
  MAX_TOTAL_CHARS,
  readFile,
  selectionProblem,
  toPayload,
  type PickedFile,
} from '../utils/uploadFiles';

const picked = (over: Partial<PickedFile> = {}): PickedFile => ({
  id: 'f',
  name: 'a.md',
  size: 10,
  type: 'auto',
  text: 'We decided X.',
  ...over,
});

describe('upload checks', () => {
  it('reads extensions in any case', () => {
    expect(extensionOf('ADR-0001.MD')).toBe('md');
    expect(extensionOf('README')).toBe('');
  });

  it('accepts markdown, text and pdf only, and at most 1 MB', () => {
    expect(checkFile('a.md', 10)).toBeNull();
    expect(checkFile('a.pdf', 10)).toBeNull();
    expect(checkFile('a.docx', 10)).toMatch(/Only \.md/);
    expect(checkFile('a.txt', MAX_FILE_BYTES + 1)).toMatch(/Larger than/);
    expect(checkFile('a.txt', 0)).toMatch(/empty/);
  });

  it('formats sizes', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(2048)).toBe('2.0 KB');
    expect(formatBytes(1_500_000)).toBe('1.5 MB');
  });

  it('limits the number of files and the total text', () => {
    expect(selectionProblem([])).toMatch(/at least one/);
    expect(selectionProblem([picked({ problem: 'bad' })])).toMatch(/at least one/);
    expect(selectionProblem([picked()])).toBeNull();
    expect(selectionProblem(Array.from({ length: MAX_FILES + 1 }, () => picked()))).toMatch(/At most 10/);
    expect(selectionProblem([picked({ text: 'x'.repeat(MAX_TOTAL_CHARS + 1) })])).toMatch(/more than 50,000/);
  });

  it('sends text files as text, pdfs as base64, and skips unreadable files', () => {
    const payload = toPayload([
      picked({ type: 'adr' }),
      picked({ name: 'b.pdf', text: undefined, pdfBase64: 'AAAA' }),
      picked({ name: 'c.docx', problem: 'no' }),
    ]);
    expect(payload).toEqual([
      { name: 'a.md', type: 'adr', text: 'We decided X.' },
      { name: 'b.pdf', type: 'auto', pdf_base64: 'AAAA' },
    ]);
  });

  it('reads a text file and flags an empty one', async () => {
    const ok = await readFile(new File(['We decided to use Kafka.'], 'notes.md'));
    expect(ok.text).toBe('We decided to use Kafka.');
    expect(ok.problem).toBeUndefined();
    const empty = await readFile(new File(['   '], 'blank.txt'));
    expect(empty.problem).toMatch(/empty/);
    const wrong = await readFile(new File(['x'], 'photo.png'));
    expect(wrong.problem).toMatch(/Only \.md/);
  });

  it('encodes a pdf as base64', async () => {
    const pdf = await readFile(new File([new Uint8Array([37, 80, 68, 70])], 'a.pdf'));
    expect(pdf.pdfBase64).toBe(btoa('%PDF'));
  });
});
