// MilestonePrompt — next step after a meaningful status change (W2-08, DOM-30).
//
//   completed → "Kunde informieren?" opens the Kundeninfo form pre-filled
//               with the latest photos ticked. Nothing is sent without an
//               explicit tap on "Erstellen & senden" (consent per send).
//   delivered → "Übergabe dokumentieren?" links to the handover step on the
//               Kunde tab; W2-11 adds the Abholprotokoll PDF and the
//               Wertgutachten as `children` (DeliveredActions).
import { useId, type ReactNode } from 'react';
import type { CustomerUpdateKind } from '../../api/customer-updates';
import type { OrderPhoto, OrderType } from '../../types';

export type Milestone = 'completed' | 'delivered';

/** Pre-filled Kundeninfo form (KundeninfoTab `initialDraft`). */
export interface KundeninfoDraft {
  kind: CustomerUpdateKind;
  subject: string;
  body: string;
  photoIds: string[];
}

export const MILESTONE_PHOTO_COUNT = 3;

function photoTime(photo: OrderPhoto): number {
  const time = new Date(photo.timestamp).getTime();
  return Number.isNaN(time) ? 0 : time;
}

/** The newest photos first, at most `count`. */
export function latestPhotoIds(photos: readonly OrderPhoto[], count = MILESTONE_PHOTO_COUNT): string[] {
  return [...photos]
    .sort((a, b) => photoTime(b) - photoTime(a))
    .slice(0, count)
    .map((photo) => String(photo.id));
}

/** Customer-facing text uses "Sie" (playbook section 11). */
export function buildCompletedDraft(
  order: Pick<OrderType, 'title' | 'customer'>,
  photos: readonly OrderPhoto[]
): KundeninfoDraft {
  const lastName = order.customer?.last_name?.trim();
  const greeting = lastName ? `Guten Tag ${lastName},` : 'Guten Tag,';
  return {
    kind: 'ready_for_pickup',
    subject: `Ihr Auftrag „${order.title}“ ist fertig`,
    body: [
      greeting,
      '',
      'Ihr Schmuckstück ist fertiggestellt und liegt zur Abholung für Sie bereit.',
      photos.length > 0 ? 'Im Anhang finden Sie Fotos des fertigen Stücks.' : null,
      '',
      'Wir freuen uns auf Ihren Besuch.',
    ]
      .filter((line): line is string => line !== null)
      .join('\n'),
    photoIds: latestPhotoIds(photos),
  };
}

interface MilestonePromptProps {
  milestone: Milestone;
  onAction: () => void;
  onDismiss: () => void;
  /** Extra next actions shown under the text (W2-11). */
  children?: ReactNode;
}

const COPY: Record<Milestone, { title: string; body: string; action: string }> = {
  completed: {
    title: 'Kunde informieren?',
    body: 'Der Auftrag ist fertiggestellt. Eine Kundeninfo „Abholbereit“ mit den neuesten Fotos ist vorbereitet; gesendet wird erst nach Ihrer Bestätigung.',
    action: 'Kundeninfo vorbereiten',
  },
  delivered: {
    title: 'Übergabe dokumentieren?',
    body: 'Der Auftrag ist ausgeliefert. Halten Sie die Übergabe an den Kunden fest.',
    action: 'Übergabe öffnen',
  },
};

export function MilestonePrompt({ milestone, onAction, onDismiss, children }: MilestonePromptProps) {
  const titleId = useId();
  const copy = COPY[milestone];
  return (
    <section className="milestone-prompt" aria-labelledby={titleId}>
      <div className="milestone-prompt-text">
        <h2 id={titleId} className="milestone-prompt-title">
          {copy.title}
        </h2>
        <p>{copy.body}</p>
        {children}
      </div>
      <div className="milestone-prompt-actions">
        <button type="button" className="btn btn-primary milestone-prompt-action" onClick={onAction}>
          {copy.action}
        </button>
        <button type="button" className="btn btn-secondary milestone-prompt-action" onClick={onDismiss}>
          Später
        </button>
      </div>
    </section>
  );
}

export default MilestonePrompt;
