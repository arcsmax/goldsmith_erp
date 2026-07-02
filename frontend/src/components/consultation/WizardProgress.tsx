import React from 'react';

interface WizardProgressProps {
  steps: { key: string; title: string }[];
  current: number; // 1-based
  onJump?: (step: number) => void;
}

export const WizardProgress: React.FC<WizardProgressProps> = ({ steps, current, onJump }) => (
  <ol className="wizard-progress" aria-label="Beratungsschritte">
    {steps.map((s, i) => {
      const n = i + 1;
      const state = n < current ? 'done' : n === current ? 'active' : 'todo';
      return (
        <li key={s.key} className={`wizard-progress-step ${state}`}>
          <button
            type="button"
            className="wizard-progress-dot"
            onClick={onJump && n < current ? () => onJump(n) : undefined}
            disabled={!onJump || n >= current}
            aria-current={n === current ? 'step' : undefined}
            aria-label={`Schritt ${n}: ${s.title}`}
          >
            {n < current ? '✓' : n}
          </button>
          <span className="wizard-progress-label">{s.title}</span>
        </li>
      );
    })}
  </ol>
);
