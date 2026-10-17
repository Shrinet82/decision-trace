import type { SourceKind } from '../api/types';

export const SOURCE_KIND_LABEL: Record<SourceKind, string> = {
  ticket: 'Ticket',
  meeting: 'Meeting notes',
  document: 'Document',
  person: 'Person record',
  team: 'Team record',
  project: 'Project record',
  system: 'System record',
};
