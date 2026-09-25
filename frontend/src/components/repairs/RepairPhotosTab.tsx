// Fotos tab of the repair page (W4-03): before / during / after comparison
// plus one upload button per phase.
//
// DESIGN_VIEW (SEC-09/GDPR-04): `repair.photos` is stripped from the backend
// response for a caller without it, so the page never mounts this tab for
// that role, and the tab still tolerates an absent array.
import React, { useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { repairPhotoPath, repairPhotoThumbPath, repairsApi } from '../../api/repairs';
import { useConfirm, useToast } from '../../contexts';
import { logError } from '../../lib/logError';
import type { RepairJob, RepairPhoto, RepairPhotoPhase } from '../../types';
import { Button } from '../../ui';
import { PhotoCompare, type PhotoItem } from '../PhotoCompare';
import { useRepairCache } from './useRepairActions';

const PHASE_LABELS: Record<RepairPhotoPhase, string> = {
  intake: 'Eingang',
  during_repair: 'Während der Reparatur',
  completed: 'Fertiggestellt',
};

const PHASES: RepairPhotoPhase[] = ['intake', 'during_repair', 'completed'];

/** Backend limit — reject client-side before any upload attempt. */
const MAX_PHOTO_BYTES = 8 * 1024 * 1024;

/**
 * thumbSrc/fullSrc route rendering through AuthenticatedImage: file_path is
 * a server-side filesystem path, not a fetchable URL.
 */
function toPhotoItem(p: RepairPhoto): PhotoItem {
  return {
    id: p.id,
    file_path: p.file_path,
    notes: p.notes,
    timestamp: p.timestamp,
    thumbSrc: repairPhotoThumbPath(p.id),
    fullSrc: repairPhotoPath(p.id),
  };
}

function usePhotoMutations(repairId: number) {
  const cache = useRepairCache(repairId);
  const { showToast } = useToast();
  const upload = useMutation({
    mutationFn: ({ file, phase }: { file: File; phase: RepairPhotoPhase }) =>
      repairsApi.uploadPhoto(repairId, file, phase),
    onSuccess: async () => {
      showToast('Foto gespeichert', 'success');
      await cache.refresh();
    },
    onError: (err) => {
      logError('RepairPhotosTab.upload', err);
      showToast('Foto konnte nicht hochgeladen werden', 'error');
    },
  });
  const remove = useMutation({
    mutationFn: (photoId: number) => repairsApi.deletePhoto(photoId),
    // Deleting a photo can reopen a linked intake-checklist item on the
    // backend — always refetch the repair, never patch locally.
    onSuccess: async () => {
      showToast('Foto gelöscht', 'success');
      await cache.refresh();
    },
    onError: (err) => {
      logError('RepairPhotosTab.delete', err);
      showToast('Foto konnte nicht gelöscht werden', 'error');
    },
  });
  return { upload, remove };
}

export const RepairPhotosTab: React.FC<{ repair: RepairJob }> = ({ repair }) => {
  const { showToast } = useToast();
  const { showConfirm } = useConfirm();
  const inputRef = useRef<HTMLInputElement>(null);
  const [pendingPhase, setPendingPhase] = useState<RepairPhotoPhase>('intake');
  const { upload, remove } = usePhotoMutations(repair.id);

  const byPhase = (phase: RepairPhotoPhase) =>
    (repair.photos ?? []).filter((p) => p.phase === phase).map(toPhotoItem);

  const pickFor = (phase: RepairPhotoPhase) => {
    setPendingPhase(phase);
    inputRef.current?.click();
  };

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (file.size > MAX_PHOTO_BYTES) {
      showToast('Datei zu groß — maximal 8 MB erlaubt', 'error');
      return;
    }
    upload.mutate({ file, phase: pendingPhase });
  };

  const handleDelete = async (photo: PhotoItem) => {
    const confirmed = await showConfirm({
      title: 'Foto löschen',
      message: 'Foto wirklich löschen?',
      confirmLabel: 'Löschen',
      variant: 'danger',
    });
    if (confirmed) remove.mutate(photo.id);
  };

  return (
    <div className="repair-tab-body">
      <h2 className="ui-visually-hidden">Fotos</h2>
      <PhotoCompare
        beforePhotos={byPhase('intake')}
        duringPhotos={byPhase('during_repair')}
        afterPhotos={byPhase('completed')}
        onDeletePhoto={(photo) => void handleDelete(photo)}
        deletingPhotoId={remove.isPending ? remove.variables : null}
      />
      <div className="repair-photo-upload" role="group" aria-label="Foto hinzufügen">
        {PHASES.map((phase) => (
          <Button
            key={phase}
            variant="secondary"
            icon="camera"
            onClick={() => pickFor(phase)}
            loading={upload.isPending && upload.variables?.phase === phase}
            disabled={upload.isPending}
          >
            Foto: {PHASE_LABELS[phase]}
          </Button>
        ))}
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="ui-visually-hidden"
          tabIndex={-1}
          aria-hidden="true"
          onChange={handleFile}
        />
      </div>
    </div>
  );
};
