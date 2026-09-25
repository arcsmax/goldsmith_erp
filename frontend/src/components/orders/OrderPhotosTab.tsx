// Fotos tab of the order page (W2-01 upload, moved out of the page in W2-08).
//
// W4-03: the photos come from the shared orderPhotosQuery (one request with
// the tab label count), the grid is a list of thumbnail buttons and the
// viewer is the src/ui Modal (focus trap, Escape, focus return, full screen
// below 600px) instead of the hand-rolled PhotoCompare lightbox.
//
// ARCH phase 4: each photo has a "Für Kunden sichtbar" checkbox
// (media_assets.customer_visible). Flagged photos are what the status report
// and a photo Kundeninfo without ticked photos send to the customer. Order
// photos are media assets with the same id.
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { OrderPhoto } from '../../types';
import { photoFilePath, photoThumbnailPath } from '../../api/photos';
import { mediaApi, type MediaAsset } from '../../api/media';
import { queryKeys } from '../../api/queryKeys';
import { logError } from '../../lib/logError';
import AuthenticatedImage from '../AuthenticatedImage';
import { Button, EmptyState, Modal } from '../../ui';
import { PhotoUpload } from './PhotoUpload';

const DATE_TIME = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeStyle: 'short' });

function photoLabel(photo: OrderPhoto, index: number): string {
  const time = new Date(photo.timestamp);
  const when = Number.isNaN(time.getTime()) ? '' : `, ${DATE_TIME.format(time)}`;
  return photo.notes ? `Foto ${index + 1}: ${photo.notes}${when}` : `Foto ${index + 1}${when}`;
}

interface PhotoViewerProps {
  photos: OrderPhoto[];
  index: number;
  onIndexChange: (index: number) => void;
  onClose: () => void;
}

function PhotoViewer({ photos, index, onIndexChange, onClose }: PhotoViewerProps) {
  const photo = photos[index];
  const count = photos.length;
  const footer =
    count > 1 ? (
      <>
        <Button
          variant="secondary"
          icon="arrow-left"
          onClick={() => onIndexChange((index - 1 + count) % count)}
        >
          Vorheriges Foto
        </Button>
        <Button variant="secondary" onClick={() => onIndexChange((index + 1) % count)}>
          Nächstes Foto
        </Button>
      </>
    ) : undefined;

  return (
    <Modal
      open
      onClose={onClose}
      title={`Foto ${index + 1} von ${count}`}
      description={photo.notes ?? undefined}
      size="lg"
      dismissOnBackdrop
      footer={footer}
      className="order-photo-viewer"
    >
      <AuthenticatedImage
        src={photoFilePath(photo.id)}
        alt={photoLabel(photo, index)}
        className="order-photo-viewer__image"
      />
    </Modal>
  );
}

interface OrderPhotosTabProps {
  orderId: number;
  photos: OrderPhoto[];
  autoCapture: boolean;
  onAutoCaptureDone: () => void;
}

const orderMediaKey = (orderId: number) => [...queryKeys.orders.photos(orderId), 'media'] as const;

function useCustomerVisibility(orderId: number) {
  const queryClient = useQueryClient();
  const key = orderMediaKey(orderId);
  const media = useQuery({
    queryKey: key,
    queryFn: () => mediaApi.listForOwner('order', orderId),
  });
  const toggle = useMutation({
    mutationFn: ({ id, visible }: { id: string; visible: boolean }) =>
      mediaApi.setCustomerVisible(id, visible),
    onSuccess: (updated: MediaAsset) => {
      queryClient.setQueryData<MediaAsset[]>(key, (current) =>
        (current ?? []).map((asset) => (asset.id === updated.id ? updated : asset))
      );
    },
    onError: (err: unknown) => logError('OrderPhotosTab.setCustomerVisible', err),
  });
  const visibleIds = new Set(
    (media.data ?? []).filter((asset) => asset.customer_visible).map((asset) => asset.id)
  );
  const knownIds = new Set((media.data ?? []).map((asset) => asset.id));
  return { visibleIds, knownIds, toggle };
}

export function OrderPhotosTab({ orderId, photos, autoCapture, onAutoCaptureDone }: OrderPhotosTabProps) {
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  const { visibleIds, knownIds, toggle } = useCustomerVisibility(orderId);

  return (
    <div className="order-tab-body order-photos-panel">
      <h2 className="ui-visually-hidden">Fotos</h2>
      <PhotoUpload orderId={orderId} autoOpen={autoCapture} onAutoOpened={onAutoCaptureDone} />
      {photos.length === 0 ? (
        <EmptyState
          icon="camera"
          title="Noch keine Fotos"
          body="Fotos vom Eingang, von Zwischenständen und vom fertigen Stück erscheinen hier."
          headingLevel={3}
        />
      ) : (
        <ul className="order-photo-grid" aria-label="Fotos des Auftrags">
          {photos.map((photo, index) => (
            <li key={photo.id}>
              <button
                type="button"
                className="order-photo-grid__item"
                onClick={() => setViewerIndex(index)}
                aria-label={`${photoLabel(photo, index)} vergrößern`}
              >
                <AuthenticatedImage
                  src={photoThumbnailPath(photo.id)}
                  alt=""
                  className="order-photo-grid__thumb"
                />
              </button>
              {knownIds.has(photo.id) && (
                <label className="order-photo-grid__visible">
                  <input
                    type="checkbox"
                    checked={visibleIds.has(photo.id)}
                    disabled={toggle.isPending}
                    onChange={(event) =>
                      toggle.mutate({ id: photo.id, visible: event.target.checked })
                    }
                    aria-label={`Foto ${index + 1} für Kunden sichtbar`}
                  />
                  <span aria-hidden="true">Für Kunden sichtbar</span>
                </label>
              )}
            </li>
          ))}
        </ul>
      )}
      {toggle.isError && (
        <p className="order-photo-grid__error" role="alert">
          Sichtbarkeit konnte nicht gespeichert werden. Bitte erneut versuchen.
        </p>
      )}
      {viewerIndex !== null && photos[viewerIndex] && (
        <PhotoViewer
          photos={photos}
          index={viewerIndex}
          onIndexChange={setViewerIndex}
          onClose={() => setViewerIndex(null)}
        />
      )}
    </div>
  );
}

export default OrderPhotosTab;
