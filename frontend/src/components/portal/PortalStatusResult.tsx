// Customer-facing status view for the public portal (playbook 5.6, W4-03).
//
// Shows only what the lookup endpoint returns for customers: reference,
// piece title, a customer-facing status label, the customer-facing step
// names and the estimated date. No internal notes, prices or staff labels.
import React from 'react';
import { StatusBadge } from '../../ui/StatusBadge';
import { Button } from '../../ui';

export interface PortalStatusResponse {
  reference_number: string;
  record_type: 'order' | 'repair';
  status_key: string;
  status_label: string;
  item_title: string;
  current_step: number;
  total_steps: number;
  step_label: string;
  pipeline_labels: string[];
  estimated_completion: string | null;
  is_complete: boolean;
  lookup_token?: string;
}

type StepState = 'done' | 'current' | 'next';

function stepState(index: number, currentStep: number, isComplete: boolean): StepState {
  // index is 0-based, currentStep is 1-based
  if (isComplete || index < currentStep - 1) return 'done';
  if (index === currentStep - 1) return 'current';
  return 'next';
}

const STEP_SYMBOL: Readonly<Record<StepState, string>> = { done: '●', current: '◉', next: '○' };
const STEP_HINT: Readonly<Record<StepState, string>> = {
  done: 'erledigt',
  current: 'aktueller Schritt',
  next: 'folgt',
};

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

interface Props {
  data: PortalStatusResponse;
  onReset: () => void;
}

export const PortalStatusResult: React.FC<Props> = ({ data, onReset }) => {
  const recordTypeLabel = data.record_type === 'repair' ? 'Ihre Reparatur' : 'Ihr Auftrag';
  const isCancelled = data.status_key === 'cancelled';
  const progressPercent =
    data.total_steps > 0
      ? Math.round((Math.max(0, data.current_step) / data.total_steps) * 100)
      : 0;

  return (
    <section className="portal-result" aria-labelledby="portal-result-title">
      <p className="portal-ref-number">
        {recordTypeLabel} · Nr. <span className="portal-num">{data.reference_number}</span>
      </p>
      <h1 id="portal-result-title" className="portal-item-title">
        {data.item_title}
      </h1>

      <StatusBadge
        kind={data.record_type}
        status={data.status_key}
        label={data.status_label}
        size="lg"
      />

      {!isCancelled && (
        <div className="portal-progress">
          <p className="portal-step-text">
            Schritt {data.current_step} von {data.total_steps}: <strong>{data.step_label}</strong>
          </p>
          <div
            className="portal-progress-track"
            role="progressbar"
            aria-label="Fortschritt"
            aria-valuenow={progressPercent}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div className="portal-progress-fill" style={{ width: `${progressPercent}%` }} />
          </div>
          <ol className="portal-steps">
            {data.pipeline_labels.map((label, i) => {
              const state = stepState(i, data.current_step, data.is_complete);
              return (
                <li
                  key={`${i}-${label}`}
                  className={`portal-step portal-step--${state}`}
                  aria-current={state === 'current' ? 'step' : undefined}
                >
                  <span className="portal-step__symbol" aria-hidden="true">
                    {STEP_SYMBOL[state]}
                  </span>
                  {label}
                  <span className="ui-visually-hidden"> ({STEP_HINT[state]})</span>
                </li>
              );
            })}
          </ol>
        </div>
      )}

      {data.estimated_completion && !data.is_complete && (
        <p className="portal-eta">
          Voraussichtlich fertig: <time className="portal-num">{formatDate(data.estimated_completion)}</time>
        </p>
      )}

      {data.is_complete && !isCancelled && (
        <p className="portal-ready">Ihr Stück ist fertig und wartet auf Sie.</p>
      )}

      <Button variant="secondary" size="lg" icon="arrow-left" onClick={onReset}>
        Anderen Auftrag prüfen
      </Button>
    </section>
  );
};
