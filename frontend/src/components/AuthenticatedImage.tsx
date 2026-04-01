// AuthenticatedImage — fetches an image via Axios (with auth header) and
// renders it via an object URL.  Necessary because <img src="..."> requests
// bypass the Axios interceptor and therefore carry no Bearer token.
import React, { useEffect, useState, useRef } from 'react';
import apiClient from '../api/client';

interface AuthenticatedImageProps {
  /** Relative path appended to the apiClient baseURL, e.g. "/orders/5/photos/1/file" */
  src: string;
  alt: string;
  className?: string;
}

const AuthenticatedImage: React.FC<AuthenticatedImageProps> = ({
  src,
  alt,
  className,
}) => {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const objectUrlRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        setIsLoading(true);
        setHasError(false);

        const response = await apiClient.get(src, {
          responseType: 'blob',
        });

        if (cancelled) return;

        const url = URL.createObjectURL(response.data as Blob);
        objectUrlRef.current = url;
        setObjectUrl(url);
      } catch {
        if (!cancelled) {
          setHasError(true);
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
      // Revoke the previous object URL to free memory
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    };
  }, [src]);

  if (isLoading) {
    return (
      <div
        className={`cdetail-timeline-thumb-placeholder ${className ?? ''}`}
        aria-label="Bild wird geladen"
        role="img"
      >
        ...
      </div>
    );
  }

  if (hasError || !objectUrl) {
    return (
      <div
        className={`cdetail-timeline-thumb-placeholder ${className ?? ''}`}
        aria-label="Kein Bild verfügbar"
        role="img"
      >
        {/* camera icon using unicode — no external dependency */}
        &#128247;
      </div>
    );
  }

  return (
    <img
      src={objectUrl}
      alt={alt}
      className={`cdetail-timeline-thumb ${className ?? ''}`}
    />
  );
};

export default AuthenticatedImage;
