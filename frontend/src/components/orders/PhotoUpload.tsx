// PhotoUpload — camera/upload control for the order Fotos tab (W2-01,
// FE-13, DOM-01).
//
// A large label wraps a hidden `<input type="file" accept="image/*"
// capture="environment" multiple>`, so on a tablet one tap opens the rear
// camera. Files upload one after another with a progress bar; a failed file
// shows its German reason (413/422 detail from the backend) and the rest
// still upload.
//
// `autoOpen` supports the scanner deep link (?tab=fotos&capture=1): the
// picker is opened once on mount. Browsers only allow that while the scan
// tap's user activation is still valid; if a browser blocks it, the big
// button stays in view as the fallback (one extra tap).
import React, { useEffect, useRef, useState } from 'react';
import {
  getPhotoSizeError,
  getPhotoUploadErrorMessage,
  photosApi,
} from '../../api/photos';
import { logError } from '../../lib/logError';
import type { OrderPhoto } from '../../types';
import '../../styles/order-detail.css';

export interface PhotoUploadProps {
  orderId: number;
  onUploaded: (photo: OrderPhoto) => void;
  /** Open the file picker once on mount (scanner deep link). */
  autoOpen?: boolean;
  /** Called after the auto-open fired, so the parent can clear its flag. */
  onAutoOpened?: () => void;
}

interface UploadProgress {
  index: number;
  total: number;
  percent: number;
}

const INPUT_ID_PREFIX = 'order-photo-upload';

function successText(count: number): string {
  return count === 1 ? '1 Foto hochgeladen' : `${count} Fotos hochgeladen`;
}

export function PhotoUpload({ orderId, onUploaded, autoOpen = false, onAutoOpened }: PhotoUploadProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const hasAutoOpenedRef = useRef(false);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [uploadedCount, setUploadedCount] = useState(0);
  const isUploading = progress !== null;
  const inputId = `${INPUT_ID_PREFIX}-${orderId}`;

  useEffect(() => {
    if (!autoOpen) {
      // Re-arm for the next deep link while this control stays mounted.
      hasAutoOpenedRef.current = false;
      return;
    }
    if (hasAutoOpenedRef.current || !inputRef.current) return;
    hasAutoOpenedRef.current = true;
    inputRef.current.click();
    onAutoOpened?.();
  }, [autoOpen, onAutoOpened]);

  const uploadOne = async (file: File, index: number, total: number): Promise<string | null> => {
    const sizeError = getPhotoSizeError(file);
    if (sizeError) return `${file.name}: ${sizeError}`;
    setProgress({ index, total, percent: 0 });
    try {
      const photo = await photosApi.upload(orderId, file, {
        onProgress: (percent) => setProgress({ index, total, percent }),
      });
      onUploaded(photo);
      return null;
    } catch (err: unknown) {
      logError('PhotoUpload.upload', err);
      return `${file.name}: ${getPhotoUploadErrorMessage(err)}`;
    }
  };

  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    const input = e.target;
    if (files.length === 0) return;
    setErrors([]);
    setUploadedCount(0);

    const failures: string[] = [];
    let successes = 0;
    for (const [i, file] of files.entries()) {
      const failure = await uploadOne(file, i + 1, files.length);
      if (failure) {
        failures.push(failure);
      } else {
        successes += 1;
      }
    }

    setProgress(null);
    setErrors(failures);
    setUploadedCount(successes);
    // Allow picking the same file again after an error.
    input.value = '';
  };

  return (
    <div className="order-photo-upload">
      <label
        htmlFor={inputId}
        className={`order-photo-upload-btn${isUploading ? ' is-busy' : ''}`}
      >
        {isUploading ? 'Foto wird hochgeladen …' : 'Foto aufnehmen'}
      </label>
      <input
        ref={inputRef}
        id={inputId}
        className="order-photo-upload-input"
        type="file"
        accept="image/*"
        capture="environment"
        multiple
        aria-label="Foto aufnehmen"
        onChange={handleChange}
        disabled={isUploading}
      />

      {progress && (
        <div className="order-photo-upload-progress" aria-live="polite">
          <span>
            Foto {progress.index} von {progress.total}: {progress.percent} %
          </span>
          <progress max={100} value={progress.percent} aria-label="Upload-Fortschritt" />
        </div>
      )}

      {!isUploading && uploadedCount > 0 && (
        <p className="order-photo-upload-success" role="status">
          {successText(uploadedCount)}
        </p>
      )}

      {errors.length > 0 && (
        <div className="order-photo-upload-error" role="alert">
          {errors.map((message) => (
            <p key={message}>{message}</p>
          ))}
        </div>
      )}
    </div>
  );
}

export default PhotoUpload;
