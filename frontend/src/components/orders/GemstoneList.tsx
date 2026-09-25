// Read-only stones of an order for the Übersicht tab (W2-06, DOM-04).
// The backend strips cost and design details by role, so a VIEWER sees
// "3 × Diamant" and the Kundenstein flag only.
import { useEffect, useId, useState } from 'react';
import { gemstonesApi, type Gemstone } from '../../api/gemstones';
import { logError } from '../../lib/logError';
import { describeGemstone } from './orderIntakeOptions';

export function GemstoneLines({ stones }: { stones: readonly Gemstone[] }) {
  if (stones.length === 0) return <p>Noch keine Steine erfasst.</p>;
  return (
    <ul className="gemstone-list">
      {stones.map((stone) => (
        <li key={stone.id}>{describeGemstone(stone)}</li>
      ))}
    </ul>
  );
}

export function GemstoneList({ orderId }: { orderId: number }) {
  const headingId = useId();
  const [stones, setStones] = useState<Gemstone[] | null>(null);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    let isCurrent = true;
    gemstonesApi
      .list(orderId)
      .then((data) => {
        if (isCurrent) setStones(data);
      })
      .catch((err: unknown) => {
        logError('GemstoneList.load', err);
        if (isCurrent) setHasError(true);
      });
    return () => {
      isCurrent = false;
    };
  }, [orderId]);

  return (
    <section className="details-section" aria-labelledby={headingId}>
      <h3 id={headingId}>Steine</h3>
      {hasError && <p role="alert">Steine konnten nicht geladen werden.</p>}
      {!hasError && stones === null && <p role="status">Steine werden geladen…</p>}
      {!hasError && stones !== null && <GemstoneLines stones={stones} />}
    </section>
  );
}

export default GemstoneList;
