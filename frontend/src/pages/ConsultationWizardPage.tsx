import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useToast } from '../contexts';
import { consultationsApi } from '../api/consultations';
import { Consultation, ConsultationUpdateInput } from '../types';
import { WizardProgress } from '../components/consultation/WizardProgress';
import { CustomerStep } from '../components/consultation/CustomerStep';
import { OccasionBudgetStep } from '../components/consultation/OccasionBudgetStep';
import { WishStep } from '../components/consultation/WishStep';
import { StyleNoGoStep } from '../components/consultation/StyleNoGoStep';
import { MeasurementStep } from '../components/consultation/MeasurementStep';
import { PhotoStep } from '../components/consultation/PhotoStep';
import { SummaryStep } from '../components/consultation/SummaryStep';
import { logError } from '../lib/logError';
import '../styles/consultations.css';

export interface WizardStepProps {
  consultation: Consultation;
  onPatch: (fields: ConsultationUpdateInput) => Promise<boolean>;
  refresh: () => Promise<void>;
}

export const WIZARD_STEPS: { key: string; title: string }[] = [
  { key: 'customer', title: 'Kundin' },
  { key: 'occasion', title: 'Anlass & Budget' },
  { key: 'wish', title: 'Der Wunsch' },
  { key: 'style', title: 'Stil & No-Gos' },
  { key: 'measurements', title: 'Maße' },
  { key: 'photos', title: 'Skizzen & Fotos' },
  { key: 'summary', title: 'Zusammenfassung' },
];

export const ConsultationWizardPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const consultationId = id ? Number(id) : null;
  // Validate the ?step= param: a non-numeric value (Number('abc') = NaN)
  // must never reach WIZARD_STEPS[step - 1] — fall back to the default.
  const rawStep = Number(searchParams.get('step'));
  const parsedStep = Number.isFinite(rawStep) && rawStep >= 1 ? rawStep : consultationId ? 2 : 1;
  const step = Math.min(Math.max(parsedStep, 1), WIZARD_STEPS.length);

  const [consultation, setConsultation] = useState<Consultation | null>(null);
  const [isLoading, setIsLoading] = useState(Boolean(consultationId));
  const [isSaving, setIsSaving] = useState(false);
  // Steps stash their pending fields here so the shared Weiter button saves
  // them. `null` is a distinct state from `{}`: it means the current step's
  // local form state is INVALID (see OccasionBudgetStep's onFieldsChange
  // contract) — {} means "valid, nothing changed, advance freely".
  const [pendingPatch, setPendingPatch] = useState<ConsultationUpdateInput | null>({});

  const refresh = useCallback(async () => {
    if (!consultationId) return;
    const data = await consultationsApi.getById(consultationId);
    setConsultation(data);
  }, [consultationId]);

  useEffect(() => {
    if (!consultationId) return;
    let cancelled = false;
    (async () => {
      try {
        setIsLoading(true);
        const data = await consultationsApi.getById(consultationId);
        if (!cancelled) setConsultation(data);
      } catch (err) {
        logError('Beratung laden fehlgeschlagen', err);
        if (!cancelled) showToast('Beratung konnte nicht geladen werden', 'error');
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [consultationId, showToast]);

  const onPatch = useCallback(
    async (fields: ConsultationUpdateInput): Promise<boolean> => {
      if (!consultationId) return false;
      if (Object.keys(fields).length === 0) return true;
      try {
        setIsSaving(true);
        const updated = await consultationsApi.update(consultationId, fields);
        setConsultation(updated);
        return true;
      } catch (err) {
        logError('Beratung speichern fehlgeschlagen', err);
        showToast('Speichern fehlgeschlagen — bitte erneut versuchen', 'error');
        return false;
      } finally {
        setIsSaving(false);
      }
    },
    [consultationId, showToast]
  );

  const goToStep = useCallback(
    (target: number) => setSearchParams({ step: String(target) }),
    [setSearchParams]
  );

  // Unified navigation used by Weiter, Zurück, AND the progress-dot jump.
  //   - pendingPatch === null (current step is INVALID): forward navigation
  //     is blocked with an error toast; backward navigation is still
  //     allowed and discards the invalid draft (leaving a broken step
  //     backward is an intentional abandonment, not a save).
  //   - pendingPatch is a (possibly empty) valid object: saved via onPatch
  //     first regardless of direction — onPatch itself is a no-op for {} —
  //     so a progress-dot jump backward never silently drops a valid,
  //     unsaved edit the way the old always-discard handleBack did.
  const navigateToStep = useCallback(
    async (target: number) => {
      if (pendingPatch === null) {
        if (target > step) {
          showToast('Bitte korrigiere die markierten Felder', 'error');
          return;
        }
        setPendingPatch({});
        goToStep(target);
        return;
      }
      const ok = await onPatch(pendingPatch);
      if (!ok) return;
      setPendingPatch({});
      goToStep(target);
    },
    [pendingPatch, onPatch, goToStep, step, showToast]
  );

  const handleNext = useCallback(() => navigateToStep(step + 1), [navigateToStep, step]);
  const handleBack = useCallback(
    () => navigateToStep(Math.max(step - 1, 1)),
    [navigateToStep, step]
  );

  // Defensive clear: browser back/forward (popstate) changes `step` without
  // ever running navigateToStep — so a pendingPatch built while editing the
  // step being left behind must never survive into the next step's Weiter
  // save.
  useEffect(() => {
    setPendingPatch({});
  }, [step]);

  // Called by the customer step (Task 3) once a customer is chosen on /new.
  const handleDraftCreated = useCallback(
    (created: Consultation) => navigate(`/consultations/${created.id}?step=2`),
    [navigate]
  );

  const stepProps: WizardStepProps | null = useMemo(
    () => (consultation ? { consultation, onPatch, refresh } : null),
    [consultation, onPatch, refresh]
  );

  // Move focus to the new step heading whenever the step changes (Weiter,
  // Zurück, progress-dot jump) so screen-reader/keyboard users land on the
  // new content instead of a now-stale focus target — but not on first
  // mount, where the natural document focus is fine.
  const stepHeadingRef = useRef<HTMLHeadingElement>(null);
  const isFirstStepRenderRef = useRef(true);
  useEffect(() => {
    if (isFirstStepRenderRef.current) {
      isFirstStepRenderRef.current = false;
      return;
    }
    stepHeadingRef.current?.focus();
  }, [step]);

  if (isLoading) return <div className="page-loading">Lade Beratung...</div>;
  if (consultationId && !consultation)
    return <div className="page-error">Beratung nicht gefunden</div>;

  const current = WIZARD_STEPS[step - 1];
  const isSummary = step === WIZARD_STEPS.length;

  return (
    <div className="wizard-container">
      <header className="wizard-header">
        <h1>Beratung</h1>
        <WizardProgress
          steps={WIZARD_STEPS}
          current={step}
          onJump={consultation ? navigateToStep : undefined}
        />
      </header>

      <section className="wizard-step" aria-labelledby="wizard-step-title">
        <h2 id="wizard-step-title" tabIndex={-1} ref={stepHeadingRef}>
          {current.title}
        </h2>
        {/* Step bodies — replaced task by task. setPendingPatch is handed to
            form steps so their local edits ride the shared Weiter autosave. */}
        {step === 1 && (
          <CustomerStep onDraftCreated={handleDraftCreated} existingCustomerId={consultation?.customer_id} />
        )}
        {step === 2 && stepProps && (
          <OccasionBudgetStep {...stepProps} onFieldsChange={setPendingPatch} />
        )}
        {step === 3 && stepProps && <WishStep {...stepProps} onFieldsChange={setPendingPatch} />}
        {step === 4 && stepProps && <StyleNoGoStep {...stepProps} />}
        {step === 5 && stepProps && <MeasurementStep customerId={stepProps.consultation.customer_id} />}
        {step === 6 && stepProps && <PhotoStep {...stepProps} />}
        {step === 7 && stepProps && <SummaryStep {...stepProps} />}
      </section>

      <footer className="wizard-footer">
        {step > 1 && consultation && (
          <button className="btn-secondary wizard-nav-btn" onClick={handleBack} disabled={isSaving}>
            Zurück
          </button>
        )}
        {!isSummary && consultation && (
          <button className="btn-primary wizard-nav-btn" onClick={handleNext} disabled={isSaving}>
            {isSaving ? 'Speichern...' : 'Weiter'}
          </button>
        )}
      </footer>
    </div>
  );
};
