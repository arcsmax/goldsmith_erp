// ConsultationWizardPage — Beratung wizard (UI-UX-PLAYBOOK 5.3, W4-03).
//
// Step bar on top, one topic per step, "Weiter" as the single primary
// action (bottom right, sticky on phone), "Zurück" never discards valid
// input. Every step change saves the step's pending fields to the draft
// (auto-save target) and a polite live region says "Wird gespeichert …" /
// "Gespeichert". The draft loads through useQuery; saves are a mutation
// that writes the answer back into the cache and invalidates the list.
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useToast } from '../contexts';
import { consultationsApi } from '../api/consultations';
import { queryKeys } from '../api/queryKeys';
import type { Consultation, ConsultationUpdateInput } from '../types';
import { WizardProgress } from '../components/consultation/WizardProgress';
import { CustomerStep } from '../components/consultation/CustomerStep';
import { OccasionBudgetStep } from '../components/consultation/OccasionBudgetStep';
import { WishStep } from '../components/consultation/WishStep';
import { StyleNoGoStep } from '../components/consultation/StyleNoGoStep';
import { MeasurementStep } from '../components/consultation/MeasurementStep';
import { PhotoStep } from '../components/consultation/PhotoStep';
import { SummaryStep } from '../components/consultation/SummaryStep';
import { logError } from '../lib/logError';
import { getErrorMessage } from '../lib/errors';
import { useDirtyGuard } from '../lib/useDirtyGuard';
import { Button, PageState, type PageStateValue } from '../ui';
import { StatusBadge } from '../ui/StatusBadge';
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

/** An existing draft resumes at step 2 (the customer is already chosen). */
const DRAFT_DEFAULT_STEP = 2;

type SaveStatus = 'idle' | 'saving' | 'saved';

const NOOP = () => undefined;

function parseStep(raw: string | null, hasConsultation: boolean): number {
  // A non-numeric value (Number('abc') = NaN) must never reach
  // WIZARD_STEPS[step - 1]; fall back to the default.
  const value = Number(raw);
  const parsed = Number.isFinite(value) && value >= 1 ? value : hasConsultation ? DRAFT_DEFAULT_STEP : 1;
  return Math.min(Math.max(parsed, 1), WIZARD_STEPS.length);
}

function useConsultation(consultationId: number | null) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const query = useQuery({
    queryKey: queryKeys.consultations.detail(consultationId ?? 0),
    queryFn: async () => {
      try {
        return await consultationsApi.getById(consultationId as number);
      } catch (err) {
        logError('Beratung laden fehlgeschlagen', err);
        throw err;
      }
    },
    enabled: consultationId !== null,
  });

  const save = useMutation({
    mutationFn: (fields: ConsultationUpdateInput) => consultationsApi.update(consultationId as number, fields),
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.consultations.detail(updated.id), updated);
      void queryClient.invalidateQueries({ queryKey: queryKeys.consultations.all, refetchType: 'none' });
    },
    onError: (err) => {
      logError('Beratung speichern fehlgeschlagen', err);
      showToast('Speichern fehlgeschlagen — bitte erneut versuchen', 'error');
    },
  });

  const onPatch = useCallback(
    async (fields: ConsultationUpdateInput): Promise<boolean> => {
      if (!consultationId) return false;
      if (Object.keys(fields).length === 0) return true;
      return save
        .mutateAsync(fields)
        .then(() => true)
        .catch(() => false);
    },
    // save.mutateAsync is stable across renders (TanStack Query).
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [consultationId, save.mutateAsync],
  );

  const { refetch } = query;
  const refresh = useCallback(async () => {
    await refetch();
  }, [refetch]);

  return { query, save, onPatch, refresh };
}

function useStepFocus(step: number) {
  // Move focus to the new step heading on every step change (Weiter,
  // Zurück, step-bar jump), but not on first mount.
  const headingRef = useRef<HTMLHeadingElement>(null);
  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    headingRef.current?.focus();
  }, [step]);
  return headingRef;
}

const SaveIndicator: React.FC<{ status: SaveStatus }> = ({ status }) => (
  <p className="wizard-save-status" role="status" aria-live="polite">
    {status === 'saving' ? 'Wird gespeichert …' : status === 'saved' ? 'Gespeichert' : ''}
  </p>
);

export const ConsultationWizardPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const consultationId = id ? Number(id) : null;
  const step = parseStep(searchParams.get('step'), Boolean(consultationId));
  const { query, save, onPatch, refresh } = useConsultation(consultationId);
  const consultation = query.data ?? null;

  // Steps stash their pending fields here so the shared Weiter button saves
  // them. `null` is a distinct state from `{}`: it means the current step's
  // local form is INVALID (see OccasionBudgetStep's onFieldsChange contract);
  // {} means "valid, nothing changed, advance freely".
  const [pendingPatch, setPendingPatch] = useState<ConsultationUpdateInput | null>({});
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const isDirty = pendingPatch === null || Object.keys(pendingPatch).length > 0;
  // Warns on reload / tab close while the step holds unsaved input.
  useDirtyGuard(isDirty, NOOP);

  const goToStep = useCallback(
    (target: number) => setSearchParams({ step: String(target) }),
    [setSearchParams],
  );

  // Unified navigation for Weiter, Zurück and the step-bar jump.
  //   - pendingPatch === null (current step INVALID): forward is blocked
  //     with an error toast; backward is allowed and drops the invalid
  //     draft (leaving a broken step backward is a deliberate abandonment).
  //   - otherwise the (possibly empty) patch is saved first in either
  //     direction, so going back never drops a valid, unsaved edit.
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
      const hasChanges = Object.keys(pendingPatch).length > 0;
      if (hasChanges) setSaveStatus('saving');
      const ok = await onPatch(pendingPatch);
      if (!ok) {
        setSaveStatus('idle');
        return;
      }
      if (hasChanges) setSaveStatus('saved');
      setPendingPatch({});
      goToStep(target);
    },
    [pendingPatch, onPatch, goToStep, step, showToast],
  );

  const handleNext = useCallback(() => navigateToStep(step + 1), [navigateToStep, step]);
  const handleBack = useCallback(() => navigateToStep(Math.max(step - 1, 1)), [navigateToStep, step]);

  // Defensive clear: browser back/forward changes `step` without running
  // navigateToStep, so a patch built on the step left behind must never
  // ride into the next step's Weiter save.
  useEffect(() => {
    setPendingPatch({});
  }, [step]);

  // Called by the customer step once a customer is chosen on /new.
  const handleDraftCreated = useCallback(
    (created: Consultation) => navigate(`/consultations/${created.id}?step=${DRAFT_DEFAULT_STEP}`),
    [navigate],
  );

  const stepProps: WizardStepProps | null = useMemo(
    () => (consultation ? { consultation, onPatch, refresh } : null),
    [consultation, onPatch, refresh],
  );
  const stepHeadingRef = useStepFocus(step);

  let loadState: PageStateValue = { status: 'ready' };
  if (consultationId && query.isPending) loadState = { status: 'loading' };
  if (consultationId && query.isError) {
    loadState = {
      status: 'error',
      error: getErrorMessage(query.error, 'Beratung konnte nicht geladen werden.'),
      retry: () => void query.refetch(),
    };
  }
  if (loadState.status !== 'ready') {
    return (
      <div className="wizard-container">
        <PageState state={loadState} skeleton="detail">
          {null}
        </PageState>
      </div>
    );
  }

  const current = WIZARD_STEPS[step - 1];
  const isSummary = step === WIZARD_STEPS.length;

  return (
    <div className="wizard-container">
      <header className="wizard-header">
        <div className="wizard-header__title">
          <h1>Beratung</h1>
          {consultation && <StatusBadge kind="consultation" status={consultation.status} />}
        </div>
        <WizardProgress steps={WIZARD_STEPS} current={step} onJump={consultation ? navigateToStep : undefined} />
      </header>

      <section className="wizard-step" aria-labelledby="wizard-step-title">
        <h2 id="wizard-step-title" tabIndex={-1} ref={stepHeadingRef}>
          {current.title}
        </h2>
        {/* setPendingPatch is handed to form steps so their local edits ride
            the shared Weiter auto-save. */}
        {step === 1 && (
          <CustomerStep onDraftCreated={handleDraftCreated} existingCustomerId={consultation?.customer_id} />
        )}
        {step === 2 && stepProps && <OccasionBudgetStep {...stepProps} onFieldsChange={setPendingPatch} />}
        {step === 3 && stepProps && <WishStep {...stepProps} onFieldsChange={setPendingPatch} />}
        {step === 4 && stepProps && <StyleNoGoStep {...stepProps} />}
        {step === 5 && stepProps && <MeasurementStep customerId={stepProps.consultation.customer_id} />}
        {step === 6 && stepProps && <PhotoStep {...stepProps} />}
        {step === 7 && stepProps && <SummaryStep {...stepProps} />}
      </section>

      {consultation && (
        <footer className="wizard-footer">
          {step > 1 ? (
            <Button variant="secondary" icon="arrow-left" onClick={handleBack} disabled={save.isPending}>
              Zurück
            </Button>
          ) : (
            <span />
          )}
          <SaveIndicator status={save.isPending ? 'saving' : saveStatus} />
          {!isSummary && (
            <Button onClick={handleNext} loading={save.isPending}>
              Weiter
            </Button>
          )}
        </footer>
      )}
    </div>
  );
};
