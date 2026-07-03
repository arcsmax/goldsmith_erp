// PhotoPicker — multi-select photo grid for attaching order photos to a
// customer update (`photo_ids` on CustomerUpdateCreate, V1.2).
//
// Selection state is CONTROLLED: the parent owns `selectedIds` and this
// component only ever calls `onChange` with a new array (never mutates the
// one it was given). Photos are loaded independently (own fetch, own error
// handling) so a load failure here can never take down the parent form.
import React, { useEffect, useState } from 'react';
import { photosApi } from '../../api/photos';
import { logError } from '../../lib/logError';
import type { OrderPhoto } from '../../types';
import AuthenticatedImage from '../AuthenticatedImage';
import './photo-picker.css';

const DEFAULT_MAX = 20;

export interface PhotoPickerProps {
  orderId: number;
  /** OrderPhoto UUIDs currently selected — owned by the parent. */
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  /** Backend cap on photo_ids length. Defaults to 20. */
  max?: number;
  disabled?: boolean;
}

/** Accessible name for a photo card: prefer the goldsmith's note, else a
 *  timestamp-based fallback so every card is announced distinctly. */
function getPhotoLabel(photo: OrderPhoto): string {
  if (photo.notes && photo.notes.trim().length > 0) {
    return photo.notes;
  }
  const parsed = new Date(photo.timestamp);
  const formatted = Number.isNaN(parsed.getTime())
    ? photo.timestamp
    : parsed.toLocaleString('de-DE');
  return `Foto vom ${formatted}`;
}

export function PhotoPicker({
  orderId,
  selectedIds,
  onChange,
  max = DEFAULT_MAX,
  disabled = false,
}: PhotoPickerProps) {
  const [photos, setPhotos] = useState<OrderPhoto[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setIsLoading(true);
      try {
        const response = await photosApi.getForOrder(orderId);
        if (!cancelled) {
          setPhotos((response.data ?? []) as OrderPhoto[]);
        }
      } catch (err) {
        logError('PhotoPicker.load', err);
        if (!cancelled) {
          setPhotos([]);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    load();

    return () => {
      cancelled = true;
    };
  }, [orderId]);

  const handleToggle = (photoId: string) => {
    if (selectedIds.includes(photoId)) {
      onChange(selectedIds.filter((id) => id !== photoId));
    } else {
      onChange([...selectedIds, photoId]);
    }
  };

  if (isLoading) {
    return (
      <div className="photo-picker photo-picker-status" aria-live="polite">
        Fotos werden geladen …
      </div>
    );
  }

  if (photos.length === 0) {
    return (
      <div className="photo-picker photo-picker-status">
        Keine Fotos für diesen Auftrag vorhanden.
      </div>
    );
  }

  const atCap = selectedIds.length >= max;

  return (
    <div className="photo-picker">
      <div className="photo-picker-header">
        <span className="photo-picker-count">
          {selectedIds.length}/{max} ausgewählt
        </span>
        {atCap && (
          <span className="photo-picker-hint" role="status">
            Maximal {max} Fotos
          </span>
        )}
      </div>
      <div className="photo-picker-grid">
        {photos.map((photo) => {
          const isSelected = selectedIds.includes(photo.id);
          const isCardDisabled = disabled || (!isSelected && atCap);
          const label = getPhotoLabel(photo);

          return (
            <button
              key={photo.id}
              type="button"
              role="checkbox"
              aria-checked={isSelected}
              aria-label={label}
              title={label}
              className={`photo-picker-thumb${
                isSelected ? ' photo-picker-thumb-selected' : ''
              }`}
              onClick={() => handleToggle(photo.id)}
              disabled={isCardDisabled}
            >
              <AuthenticatedImage
                src={`/photos/${photo.id}/thumbnail`}
                alt={label}
                className="photo-picker-thumb-img"
              />
              {isSelected && (
                <span className="photo-picker-thumb-check" aria-hidden="true">
                  &#10003;
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default PhotoPicker;
