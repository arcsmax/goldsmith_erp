// PhotoCompare — side-by-side Vorher/Nachher photo comparison with lightbox
// Accepts typed photo arrays. For repairs: phase-filtered RepairPhoto[].
// For orders: flat OrderPhoto[] (all shown as a uniform grid).
import React, { useCallback, useEffect, useState } from 'react';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface PhotoItem {
  id: number;
  file_path: string;
  notes?: string | null;
  timestamp?: string;
}

export interface PhotoCompareProps {
  /** Left column — "Vorher (Eingang)" */
  beforePhotos: PhotoItem[];
  /** Right column — "Nachher (Fertig)" */
  afterPhotos: PhotoItem[];
  /** Optional middle column — "Während Reparatur" */
  duringPhotos?: PhotoItem[];
  /** Compact single-grid mode (no before/after split — used by OrderDetailPage) */
  gridMode?: boolean;
  /** All photos for gridMode */
  allPhotos?: PhotoItem[];
}

// ─── Lightbox ────────────────────────────────────────────────────────────────

interface LightboxProps {
  photos: PhotoItem[];
  startIndex: number;
  onClose: () => void;
}

function Lightbox({ photos, startIndex, onClose }: LightboxProps) {
  const [index, setIndex] = useState(startIndex);

  const prev = useCallback(() =>
    setIndex(i => (i - 1 + photos.length) % photos.length), [photos.length]);
  const next = useCallback(() =>
    setIndex(i => (i + 1) % photos.length), [photos.length]);

  // Keyboard navigation
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowLeft') prev();
      if (e.key === 'ArrowRight') next();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose, prev, next]);

  const photo = photos[index];
  const isViewable =
    photo.file_path.startsWith('blob:') ||
    photo.file_path.startsWith('/') ||
    photo.file_path.startsWith('http');

  return (
    <div
      className="photo-lightbox-overlay"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
      role="dialog"
      aria-modal="true"
      aria-label="Foto vergroessert"
    >
      <div className="photo-lightbox-box">
        {/* Header */}
        <div className="photo-lightbox-header">
          <span className="photo-lightbox-counter">
            {index + 1} / {photos.length}
            {photo.notes && <span className="photo-lightbox-notes"> &mdash; {photo.notes}</span>}
          </span>
          <button
            className="photo-lightbox-close"
            onClick={onClose}
            aria-label="Schliessen"
          >
            &#x2715;
          </button>
        </div>

        {/* Image */}
        <div className="photo-lightbox-image-wrap">
          {isViewable ? (
            <img
              src={photo.file_path}
              alt={photo.notes ?? 'Foto'}
              className="photo-lightbox-image"
            />
          ) : (
            <div className="photo-lightbox-no-preview">
              <span style={{ fontSize: '3rem' }}>&#128247;</span>
              <p>{photo.notes ?? photo.file_path.split('/').pop()}</p>
              <p style={{ fontSize: '0.8rem', opacity: 0.6 }}>Vorschau nicht verfuegbar</p>
            </div>
          )}
        </div>

        {/* Navigation */}
        {photos.length > 1 && (
          <div className="photo-lightbox-nav">
            <button
              className="photo-lightbox-nav-btn"
              onClick={prev}
              aria-label="Vorheriges Foto"
            >
              &#8592;
            </button>
            <button
              className="photo-lightbox-nav-btn"
              onClick={next}
              aria-label="Naechstes Foto"
            >
              &#8594;
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Single photo thumbnail ───────────────────────────────────────────────────

interface ThumbProps {
  photo: PhotoItem;
  onClick: () => void;
}

function PhotoThumb({ photo, onClick }: ThumbProps) {
  const isViewable =
    photo.file_path.startsWith('blob:') ||
    photo.file_path.startsWith('/') ||
    photo.file_path.startsWith('http');

  return (
    <button
      className="photo-compare-thumb"
      onClick={onClick}
      title={photo.notes ?? 'Foto vergroessern'}
      aria-label={photo.notes ?? 'Foto vergroessern'}
    >
      {isViewable ? (
        <img
          src={photo.file_path}
          alt={photo.notes ?? 'Foto'}
          className="photo-compare-thumb-img"
        />
      ) : (
        <div className="photo-compare-thumb-placeholder">
          <span style={{ fontSize: '1.5rem' }}>&#128247;</span>
          <span>{photo.notes ?? photo.file_path.split('/').pop()}</span>
        </div>
      )}
      <div className="photo-compare-thumb-hover-overlay">
        <span>&#128269;</span>
      </div>
    </button>
  );
}

// ─── Column component ─────────────────────────────────────────────────────────

interface ColumnProps {
  label: string;
  sublabel?: string;
  photos: PhotoItem[];
  emptyMessage: string;
  /** All photos in this column, used for lightbox index calculation */
  allColumnPhotos: PhotoItem[];
  onOpenLightbox: (photos: PhotoItem[], index: number) => void;
  highlightEmpty?: boolean;
}

function PhotoColumn({
  label,
  sublabel,
  photos,
  emptyMessage,
  allColumnPhotos,
  onOpenLightbox,
  highlightEmpty,
}: ColumnProps) {
  return (
    <div className="photo-compare-column">
      <div className="photo-compare-column-header">
        <span className="photo-compare-column-label">{label}</span>
        {sublabel && (
          <span className="photo-compare-column-sublabel">{sublabel}</span>
        )}
        <span className="photo-compare-column-count">
          {photos.length} {photos.length === 1 ? 'Foto' : 'Fotos'}
        </span>
      </div>

      {photos.length === 0 ? (
        <div
          className={`photo-compare-empty${highlightEmpty ? ' photo-compare-empty--after' : ''}`}
        >
          <span style={{ fontSize: '2rem', opacity: 0.35 }}>&#128247;</span>
          <p>{emptyMessage}</p>
        </div>
      ) : (
        <div className="photo-compare-grid">
          {photos.map((photo, i) => (
            <PhotoThumb
              key={photo.id}
              photo={photo}
              onClick={() => onOpenLightbox(allColumnPhotos, i)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function PhotoCompare({
  beforePhotos,
  afterPhotos,
  duringPhotos = [],
  gridMode = false,
  allPhotos = [],
}: PhotoCompareProps) {
  const [lightbox, setLightbox] = useState<{
    photos: PhotoItem[];
    index: number;
  } | null>(null);

  const openLightbox = useCallback((photos: PhotoItem[], index: number) => {
    setLightbox({ photos, index });
  }, []);

  // Grid mode — flat photo grid (used by OrderDetailPage)
  if (gridMode) {
    if (allPhotos.length === 0) {
      return (
        <div className="photo-compare-empty photo-compare-empty--center">
          <span style={{ fontSize: '2.5rem', opacity: 0.3 }}>&#128247;</span>
          <p>Noch keine Fotos vorhanden</p>
        </div>
      );
    }
    return (
      <>
        <div className="photo-compare-flat-grid">
          {allPhotos.map((photo, i) => (
            <PhotoThumb
              key={photo.id}
              photo={photo}
              onClick={() => openLightbox(allPhotos, i)}
            />
          ))}
        </div>
        {lightbox && (
          <Lightbox
            photos={lightbox.photos}
            startIndex={lightbox.index}
            onClose={() => setLightbox(null)}
          />
        )}
      </>
    );
  }

  // Before/After comparison mode (used by RepairDetailPage)
  const hasDuring = duringPhotos.length > 0;
  const columnCount = hasDuring ? 3 : 2;

  return (
    <>
      <div
        className="photo-compare-layout"
        style={{ '--photo-compare-columns': columnCount } as React.CSSProperties}
      >
        <PhotoColumn
          label="Vorher"
          sublabel="Eingang"
          photos={beforePhotos}
          emptyMessage="Keine Eingangsfotos vorhanden"
          allColumnPhotos={beforePhotos}
          onOpenLightbox={openLightbox}
        />

        {hasDuring && (
          <PhotoColumn
            label="Waehrend"
            sublabel="Reparatur"
            photos={duringPhotos}
            emptyMessage="Keine Zwischenfotos vorhanden"
            allColumnPhotos={duringPhotos}
            onOpenLightbox={openLightbox}
          />
        )}

        <PhotoColumn
          label="Nachher"
          sublabel="Fertig"
          photos={afterPhotos}
          emptyMessage="Noch keine Fotos nach Fertigstellung"
          allColumnPhotos={afterPhotos}
          onOpenLightbox={openLightbox}
          highlightEmpty={afterPhotos.length === 0}
        />
      </div>

      {lightbox && (
        <Lightbox
          photos={lightbox.photos}
          startIndex={lightbox.index}
          onClose={() => setLightbox(null)}
        />
      )}
    </>
  );
}
