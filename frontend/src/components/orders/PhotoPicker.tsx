// PhotoPicker — multi-select photo grid for attaching order photos to a
// customer update (`photo_ids` on CustomerUpdateCreate, V1.2).
//
// Selection state is CONTROLLED: the parent owns `selectedIds` and this
// component only ever calls `onChange` with a new array (never mutates the
// one it was given). Photos come from the shared order-photos query (one
// request with the Fotos tab, W4-03). A load failure is logged and shown as
// the empty guidance, so it can never take down the parent form.
import { useQuery } from '@tanstack/react-query';
import { photosApi } from '../../api/photos';
import { logError } from '../../lib/logError';
import type { OrderPhoto } from '../../types';
import { EmptyState, Icon, PageState } from '../../ui';
import AuthenticatedImage from '../AuthenticatedImage';
import { orderPhotosQuery } from './orderQueries';
import './photo-picker.css';

const DEFAULT_MAX = 20;

const EMPTY_BODY =
  'Für diesen Auftrag sind noch keine Fotos hinterlegt. Fotos werden im Tab „Fotos" hochgeladen und können hier anschließend ausgewählt werden.';

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

/** Same key and request as the page's photo query; logs a failed load here. */
function usePickerPhotos(orderId: number) {
  const base = orderPhotosQuery(orderId);
  return useQuery({
    queryKey: base.queryKey,
    queryFn: async (): Promise<OrderPhoto[]> => {
      try {
        return (await photosApi.getForOrder(orderId)).data ?? [];
      } catch (err: unknown) {
        logError('PhotoPicker.load', err);
        throw err;
      }
    },
  });
}

export function PhotoPicker({
  orderId,
  selectedIds,
  onChange,
  max = DEFAULT_MAX,
  disabled = false,
}: PhotoPickerProps) {
  const query = usePickerPhotos(orderId);
  const photos = query.data ?? [];

  const handleToggle = (photoId: string) => {
    if (selectedIds.includes(photoId)) {
      onChange(selectedIds.filter((id) => id !== photoId));
    } else {
      onChange([...selectedIds, photoId]);
    }
  };

  if (query.isPending) {
    return <PageState state={{ status: 'loading' }} skeleton="cards" skeletonCount={3} />;
  }

  if (photos.length === 0) {
    return (
      <EmptyState icon="camera" title="Noch keine Fotos" body={EMPTY_BODY} headingLevel={3} />
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
              className={`photo-picker-thumb${isSelected ? ' photo-picker-thumb-selected' : ''}`}
              onClick={() => handleToggle(photo.id)}
              disabled={isCardDisabled}
            >
              <AuthenticatedImage
                src={`/photos/${photo.id}/thumbnail`}
                alt={label}
                className="photo-picker-thumb-img"
              />
              {isSelected && (
                <span className="photo-picker-thumb-check">
                  <Icon name="check" />
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
