// PhotoStep — Beratungs-Wizard step 6: Skizzen & Fotos.
//
// Unlike the consultation-field steps (2, 3), this step has no pendingPatch:
// every upload/delete hits its own endpoint immediately and calls refresh()
// to pull the updated consultation.photos list — same immediate-persistence
// shape as StyleNoGoStep. This is the first REAL photo upload in the
// frontend (real multipart via consultationsApi.uploadPhoto, Task 1). The
// hidden-input/label UX shape mirrors RepairDetailPage.tsx:399-411, but that
// page's upload is a blob-URL placeholder — do not copy that part.
import React, { useState } from 'react';
import type { WizardStepProps } from '../../pages/ConsultationWizardPage';
import { consultationsApi, consultationPhotoThumbPath } from '../../api/consultations';
import { ConsultationPhoto, ConsultationPhotoKind } from '../../types';
import { useConfirm, useToast } from '../../contexts';
import { logError } from '../../lib/logError';
import AuthenticatedImage from '../AuthenticatedImage';

/** Exported for reuse by the summary step (Task 8). */
export const PHOTO_KIND_LABELS: Record<ConsultationPhotoKind, string> = {
  sketch: 'Skizze',
  reference: 'Referenz',
  inspiration: 'Inspiration',
  existing_piece: 'Mitgebrachtes Stück',
};

const PHOTO_KIND_KEYS = Object.keys(PHOTO_KIND_LABELS) as ConsultationPhotoKind[];

/** Backend limit — reject client-side before any upload attempt. */
const MAX_PHOTO_BYTES = 8 * 1024 * 1024;

export const PhotoStep: React.FC<WizardStepProps> = ({ consultation, refresh }) => {
  const { showToast } = useToast();
  const { showConfirm } = useConfirm();
  const [selectedKind, setSelectedKind] = useState<ConsultationPhotoKind>('sketch');
  const [isUploading, setIsUploading] = useState(false);
  const [deletingPhotoId, setDeletingPhotoId] = useState<string | null>(null);

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > MAX_PHOTO_BYTES) {
      showToast('Datei zu groß — maximal 8 MB erlaubt', 'error');
      e.target.value = '';
      return;
    }

    setIsUploading(true);
    try {
      await consultationsApi.uploadPhoto(consultation.id, file, selectedKind, undefined);
      await refresh();
    } catch (err) {
      logError('Foto hochladen fehlgeschlagen', err);
      showToast('Foto konnte nicht hochgeladen werden', 'error');
    } finally {
      setIsUploading(false);
      e.target.value = '';
    }
  };

  const handleDelete = async (photo: ConsultationPhoto) => {
    const confirmed = await showConfirm({
      title: 'Foto löschen',
      message: 'Foto wirklich löschen?',
      confirmLabel: 'Löschen',
      variant: 'danger',
    });
    if (!confirmed) return;

    setDeletingPhotoId(photo.id);
    try {
      await consultationsApi.deletePhoto(photo.id);
      await refresh();
    } catch (err) {
      logError('Foto löschen fehlgeschlagen', err);
      showToast('Foto konnte nicht gelöscht werden', 'error');
    } finally {
      setDeletingPhotoId(null);
    }
  };

  return (
    <div className="photo-step">
      <div className="wizard-field">
        <label id="photo-kind-label">Art</label>
        <div className="chip-group" role="group" aria-labelledby="photo-kind-label">
          {PHOTO_KIND_KEYS.map((key) => (
            <button
              key={key}
              type="button"
              className={`chip${selectedKind === key ? ' selected' : ''}`}
              aria-pressed={selectedKind === key}
              onClick={() => setSelectedKind(key)}
            >
              {PHOTO_KIND_LABELS[key]}
            </button>
          ))}
        </div>
      </div>

      <div className="consultation-photo-grid">
        <label className="photo-upload-tile" htmlFor="photo-upload-input">
          <input
            id="photo-upload-input"
            type="file"
            accept="image/*"
            capture="environment"
            style={{ display: 'none' }}
            onChange={handleFileSelect}
            disabled={isUploading}
          />
          {isUploading ? (
            <span>Wird hochgeladen…</span>
          ) : (
            <>
              <span aria-hidden="true">+</span>
              <span>Foto hinzufügen</span>
            </>
          )}
        </label>

        {consultation.photos.map((photo) => (
          <div className="consultation-photo-card" key={photo.id}>
            <AuthenticatedImage
              src={consultationPhotoThumbPath(photo.id)}
              alt={PHOTO_KIND_LABELS[photo.kind]}
            />
            <span className="consultation-photo-kind">{PHOTO_KIND_LABELS[photo.kind]}</span>
            <button
              type="button"
              className="consultation-photo-delete"
              onClick={() => handleDelete(photo)}
              disabled={deletingPhotoId === photo.id}
              aria-label="Foto löschen"
            >
              {deletingPhotoId === photo.id ? '...' : '×'}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};
