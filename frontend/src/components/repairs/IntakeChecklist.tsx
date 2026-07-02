// IntakeChecklist — Eingangs-Checkliste on RepairDetailPage.
//
// Dispute protection mirroring insurance-industry intake practice: every
// item must be satisfied EITHER by an intake-phase photo OR an explicit
// "nicht zutreffend" declaration with a reason (>=3 chars). Mirrors backend
// IntakeChecklistItem (src/goldsmith_erp/models/repair.py) and the PUT
// /repairs/{id}/intake-checklist contract, which is a FULL list replace —
// every mutation here resubmits the complete items array.
//
// Upload + PUT pattern mirrors PhotoStep.tsx (consultation photos): real
// multipart upload via repairsApi.uploadPhoto, 8MB client-side guard,
// logError for all failures. The PUT response is a full RepairJobRead
// (photos + checklist), so the parent just replaces its whole `repair`
// state via onUpdated — no local patching.
import React, { useState } from 'react';
import { repairsApi, repairPhotoThumbPath } from '../../api/repairs';
import { IntakeChecklistItem, RepairJob } from '../../types';
import { useToast } from '../../contexts';
import { logError } from '../../lib/logError';
import AuthenticatedImage from '../AuthenticatedImage';

/** Backend limit — reject client-side before any upload attempt. */
const MAX_PHOTO_BYTES = 8 * 1024 * 1024;

const STATUS_CHIP_LABELS: Record<IntakeChecklistItem['status'], string> = {
  open: 'Offen',
  photo: 'Foto ✓',
  na: 'N. z.',
};

const MIN_REASON_LENGTH = 3;

interface IntakeChecklistProps {
  repair: RepairJob;
  /** Called with the full, fresh RepairJob after every successful mutation. */
  onUpdated: (repair: RepairJob) => void;
}

interface IntakeChecklistRowProps {
  item: IntakeChecklistItem;
  busy: boolean;
  reasonOpen: boolean;
  reasonDraft: string;
  onReasonDraftChange: (value: string) => void;
  onOpenReason: () => void;
  onCancelReason: () => void;
  onPhotoCapture: (file: File) => void;
  onSubmitReason: () => void;
}

function IntakeChecklistRow({
  item,
  busy,
  reasonOpen,
  reasonDraft,
  onReasonDraftChange,
  onOpenReason,
  onCancelReason,
  onPhotoCapture,
  onSubmitReason,
}: IntakeChecklistRowProps) {
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    onPhotoCapture(file);
  };

  return (
    <li className={`intake-checklist-row intake-checklist-row--${item.status}`}>
      <div className="intake-checklist-row-main">
        <span className="intake-checklist-row-label">{item.label}</span>
        <span className={`intake-checklist-chip intake-checklist-chip--${item.status}`}>
          {STATUS_CHIP_LABELS[item.status]}
        </span>
      </div>

      {item.status === 'open' && !reasonOpen && (
        <div className="intake-checklist-row-actions">
          <label className="intake-checklist-photo-btn" htmlFor={`intake-photo-${item.key}`}>
            <input
              id={`intake-photo-${item.key}`}
              type="file"
              accept="image/*"
              capture="environment"
              style={{ display: 'none' }}
              onChange={handleFileChange}
              disabled={busy}
            />
            {busy ? 'Wird hochgeladen…' : 'Foto aufnehmen'}
          </label>
          <button
            type="button"
            className="intake-checklist-na-btn"
            onClick={onOpenReason}
            disabled={busy}
          >
            Nicht zutreffend
          </button>
        </div>
      )}

      {item.status === 'open' && reasonOpen && (
        <div className="intake-checklist-reason-form">
          <input
            type="text"
            className="form-input"
            placeholder="Begründung (mind. 3 Zeichen)"
            value={reasonDraft}
            onChange={(e) => onReasonDraftChange(e.target.value)}
            disabled={busy}
            autoFocus
          />
          <div className="intake-checklist-reason-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onCancelReason}
              disabled={busy}
            >
              Abbrechen
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={onSubmitReason}
              disabled={busy || reasonDraft.trim().length < MIN_REASON_LENGTH}
            >
              {busy ? 'Wird gespeichert…' : 'Speichern'}
            </button>
          </div>
        </div>
      )}

      {item.status === 'photo' && item.photo_id != null && (
        <div className="intake-checklist-row-photo">
          <AuthenticatedImage
            src={repairPhotoThumbPath(item.photo_id)}
            alt={item.label}
            className="intake-checklist-thumb"
          />
        </div>
      )}

      {item.status === 'na' && item.na_reason && (
        <p className="intake-checklist-na-reason">{item.na_reason}</p>
      )}
    </li>
  );
}

export function IntakeChecklist({ repair, onUpdated }: IntakeChecklistProps) {
  const { showToast } = useToast();
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [reasonDraft, setReasonDraft] = useState<Record<string, string>>({});
  const [openReasonKey, setOpenReasonKey] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(true);

  const items = repair.intake_checklist;

  if (!items || items.length === 0) {
    return (
      <div className="intake-checklist intake-checklist--empty">
        <p>Keine Eingangs-Checkliste hinterlegt.</p>
      </div>
    );
  }

  const doneCount = items.filter((i) => i.status !== 'open').length;
  const allDone = doneCount === items.length;

  const handlePhotoCapture = async (item: IntakeChecklistItem, file: File) => {
    if (file.size > MAX_PHOTO_BYTES) {
      showToast('Datei zu groß — maximal 8 MB erlaubt', 'error');
      return;
    }
    setBusyKey(item.key);
    try {
      const photo = await repairsApi.uploadPhoto(repair.id, file, 'intake');
      const nextItems: IntakeChecklistItem[] = items.map((i) =>
        i.key === item.key
          ? { key: i.key, label: i.label, status: 'photo', photo_id: photo.id }
          : i
      );
      const updated = await repairsApi.updateIntakeChecklist(repair.id, nextItems);
      onUpdated(updated);
    } catch (err) {
      logError('Checklisten-Foto fehlgeschlagen', err);
      showToast('Foto konnte nicht hochgeladen werden', 'error');
    } finally {
      setBusyKey(null);
    }
  };

  const handleNotApplicable = async (item: IntakeChecklistItem, reason: string) => {
    const trimmed = reason.trim();
    if (trimmed.length < MIN_REASON_LENGTH) {
      showToast('Begründung muss mindestens 3 Zeichen haben', 'error');
      return;
    }
    setBusyKey(item.key);
    try {
      const nextItems: IntakeChecklistItem[] = items.map((i) =>
        i.key === item.key
          ? { key: i.key, label: i.label, status: 'na', na_reason: trimmed }
          : i
      );
      const updated = await repairsApi.updateIntakeChecklist(repair.id, nextItems);
      onUpdated(updated);
      setOpenReasonKey(null);
      setReasonDraft((prev) => ({ ...prev, [item.key]: '' }));
    } catch (err) {
      logError('Checkliste aktualisieren fehlgeschlagen', err);
      showToast('Konnte nicht als "nicht zutreffend" markiert werden', 'error');
    } finally {
      setBusyKey(null);
    }
  };

  if (allDone && !expanded) {
    return (
      <div className="intake-checklist intake-checklist--collapsed">
        <button
          type="button"
          className="intake-checklist-summary"
          onClick={() => setExpanded(true)}
        >
          <span className="intake-checklist-summary-check" aria-hidden="true">
            ✓
          </span>
          <span>
            {doneCount}/{items.length} erledigt
          </span>
          <span className="intake-checklist-summary-toggle">Anzeigen</span>
        </button>
      </div>
    );
  }

  return (
    <div className="intake-checklist">
      <div className="intake-checklist-header">
        <h3>Eingangs-Checkliste</h3>
        <span className="intake-checklist-progress">
          {doneCount}/{items.length} erledigt
        </span>
        {allDone && (
          <button
            type="button"
            className="intake-checklist-collapse-btn"
            onClick={() => setExpanded(false)}
          >
            Einklappen
          </button>
        )}
      </div>
      <ul className="intake-checklist-list">
        {items.map((item) => (
          <IntakeChecklistRow
            key={item.key}
            item={item}
            busy={busyKey === item.key}
            reasonOpen={openReasonKey === item.key}
            reasonDraft={reasonDraft[item.key] ?? ''}
            onReasonDraftChange={(value) =>
              setReasonDraft((prev) => ({ ...prev, [item.key]: value }))
            }
            onOpenReason={() => setOpenReasonKey(item.key)}
            onCancelReason={() => {
              setOpenReasonKey(null);
              setReasonDraft((prev) => ({ ...prev, [item.key]: '' }));
            }}
            onPhotoCapture={(file) => handlePhotoCapture(item, file)}
            onSubmitReason={() => handleNotApplicable(item, reasonDraft[item.key] ?? '')}
          />
        ))}
      </ul>
    </div>
  );
}
