import type { IngestRequest, IngestSourceType } from '../../api/types';

export const MAX_TEXT = 5000;

export const TYPE_LABEL: Record<IngestSourceType, string> = {
  meeting: 'Meeting',
  ticket: 'Ticket',
  announcement: 'Announcement',
};

export interface IngestForm {
  type: IngestSourceType;
  title: string;
  date: string;
  text: string;
  participants: string;
}

export const PRESETS: { label: string; form: IngestForm }[] = [
  {
    label: 'Arch sync: standardise on Kafka',
    form: {
      type: 'meeting',
      title: 'Architecture sync',
      date: '2026-10-16',
      text: 'Architecture sync, 2026-10-16. Attendees: Alice Vance, Bob Martin, Kevin Flynn. Decision: we standardise on Kafka for all event messaging across services. RabbitMQ is retired; Bob agreed to migrate remaining queues by Q1. Owner: Alice Vance.',
      participants: 'Alice Vance, Bob Martin, Kevin Flynn',
    },
  },
  {
    label: 'HR: Alice Vance leaves',
    form: {
      type: 'announcement',
      title: 'People update: Alice Vance',
      date: '2026-10-16',
      text: 'People update, 2026-10-16: Alice Vance has left the company effective today. Her responsibilities are pending reassignment.',
      participants: '',
    },
  },
];

/** Today's date in local time as YYYY-MM-DD. */
export function todayIso(now = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export const emptyForm = (): IngestForm => ({ type: 'meeting', title: '', date: todayIso(), text: '', participants: '' });

export function toIngestRequest(form: IngestForm): IngestRequest {
  const participants = form.participants
    .split(',')
    .map((p) => p.trim())
    .filter(Boolean);
  return {
    type: form.type,
    title: form.title.trim(),
    date: form.date,
    text: form.text.trim(),
    ...(participants.length > 0 ? { participants } : {}),
  };
}
