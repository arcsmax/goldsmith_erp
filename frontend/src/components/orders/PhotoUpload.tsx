// PhotoUpload — camera/upload control for the order Fotos tab (W2-01,
// FE-13, DOM-01; primitives + mutation W4-03).
//
// A large Button opens a hidden `<input type="file" accept="image/*"
// capture="environment" multiple>`, so on a tablet one tap opens the rear
// camera. Files upload one after another with a progress bar; a failed file
// shows its German reason (413/422 detail from the backend) and the rest
// still upload. Each uploaded photo is appended to the shared photo query
// cache and the Verlauf is refreshed.
//
// `autoOpen` supports the scanner deep link (?tab=fotos&capture=1): the
// picker is opened once on mount. Browsers only allow that while the scan
// tap's user activation is still valid; if a browser blocks it, the big
// button stays in view as the fallback (one extra tap).
import React, { useEffect, useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getPhotoSizeError,
  getPhotoUploadErrorMessage,
  photosApi,
} from '../../api/photos';
import { queryKeys } from '../../api/queryKeys';
import { logError } from '../../lib/logError';
import type { OrderPhoto } from '../../types';
import { Button } from '../../ui';
import './photo-picker.css';

export interface PhotoUploadProps {
  orderId: number;
  onUploaded?: (photo: OrderPhoto) => void;
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

interface UploadVariables {
  file: File;
  index: number;
  total: number;
}

const INPUT_ID_PREFIX = 'order-photo-upload';

function successText(count: number): string {
  return count === 1 ? '1 Foto hochgeladen' : `${count} Fotos hochgeladen`;
}

function appendPhoto(prev: OrderPhoto[] | undefined, photo: OrderPhoto): OrderPhoto[] | undefined {
  if (!prev) return prev;
  return prev.some((p) => p.id === photo.id) ? prev : [...prev, photo];
}

function useAutoOpen(
  inputRef: React.RefObject<HTMLInputElement | null>,
  autoOpen: boolean,
  onAutoOpened?: () => void,
): void {
  const hasAutoOpenedRef = useRef(false);
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
  }, [autoOpen, onAutoOpened, inputRef]);
}

export function PhotoUpload({ orderId, onUploaded, autoOpen = false, onAutoOpened }: PhotoUploadProps) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [uploadedCount, setUploadedCount] = useState(0);
  const isUploading = progress !== null;
  const inputId = `${INPUT_ID_PREFIX}-${orderId}`;

  useAutoOpen(inputRef, autoOpen, onAutoOpened);

  const upload = useMutation({
    mutationFn: ({ file, index, total }: UploadVariables) =>
      photosApi.upload(orderId, file, {
        onProgress: (percent) => setProgress({ index, total, percent }),
      }),
    onSuccess: (photo) => {
      queryClient.setQueryData<OrderPhoto[]>(queryKeys.orders.photos(orderId), (prev) =>
        appendPhoto(prev, photo),
      );
      void queryClient.invalidateQueries({ queryKey: queryKeys.orders.timeline(orderId) });
      onUploaded?.(photo);
    },
  });

  const uploadOne = async (file: File, index: number, total: number): Promise<string | null> => {
    const sizeError = getPhotoSizeError(file);
    if (sizeError) return `${file.name}: ${sizeError}`;
    setProgress({ index, total, percent: 0 });
    try {
      await upload.mutateAsync({ file, index, total });
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
      if (failure) failures.push(failure);
      else successes += 1;
    }

    setProgress(null);
    setErrors(failures);
    setUploadedCount(successes);
    // Allow picking the same file again after an error.
    input.value = '';
  };

  return (
    <div className="photo-upload">
      <Button
        size="lg"
        icon="camera"
        loading={isUploading}
        aria-controls={inputId}
        onClick={() => inputRef.current?.click()}
      >
        {isUploading ? 'Foto wird hochgeladen…' : 'Foto aufnehmen'}
      </Button>
      <input
        ref={inputRef}
        id={inputId}
        className="ui-visually-hidden"
        tabIndex={-1}
        type="file"
        accept="image/*"
        capture="environment"
        multiple
        aria-label="Foto aufnehmen"
        onChange={handleChange}
        disabled={isUploading}
      />

      {progress && (
        <div className="photo-upload-progress" aria-live="polite">
          <span className="photo-upload-progress-text">
            Foto {progress.index} von {progress.total}: {progress.percent} %
          </span>
          <progress max={100} value={progress.percent} aria-label="Upload-Fortschritt" />
        </div>
      )}

      {!isUploading && uploadedCount > 0 && (
        <p className="photo-upload-success" role="status">
          {successText(uploadedCount)}
        </p>
      )}

      {errors.length > 0 && (
        <div className="photo-upload-error" role="alert">
          {errors.map((message) => (
            <p key={message}>{message}</p>
          ))}
        </div>
      )}
    </div>
  );
}

export default PhotoUpload;
