// Fotos tab of the order page (W2-01 upload, moved out of the page in W2-08).
import type { OrderPhoto } from '../../types';
import { PhotoCompare, type PhotoItem } from '../PhotoCompare';
import { photoFilePath, photoThumbnailPath } from '../../api/photos';
import { PhotoUpload } from './PhotoUpload';

/** Order photos → PhotoCompare items: stable keys, authenticated URLs. */
function toOrderPhotoItem(photo: OrderPhoto, index: number): PhotoItem {
  return {
    id: index + 1,
    renderKey: photo.id,
    file_path: photo.file_path,
    notes: photo.notes,
    timestamp: photo.timestamp,
    thumbSrc: photoThumbnailPath(photo.id),
    fullSrc: photoFilePath(photo.id),
  };
}

interface OrderPhotosTabProps {
  orderId: number;
  photos: OrderPhoto[];
  autoCapture: boolean;
  onAutoCaptureDone: () => void;
  onPhotoUploaded: (photo: OrderPhoto) => void;
}

export function OrderPhotosTab({
  orderId,
  photos,
  autoCapture,
  onAutoCaptureDone,
  onPhotoUploaded,
}: OrderPhotosTabProps) {
  return (
    <div className="tab-panel order-photos-panel">
      <h2>Fotos</h2>
      <PhotoUpload
        orderId={orderId}
        onUploaded={onPhotoUploaded}
        autoOpen={autoCapture}
        onAutoOpened={onAutoCaptureDone}
      />
      <PhotoCompare beforePhotos={[]} afterPhotos={[]} gridMode allPhotos={photos.map(toOrderPhotoItem)} />
    </div>
  );
}

export default OrderPhotosTab;
