// KundeninfoMessageAids — consent / delivery hints and the email preview for
// the Kundeninfo composer (W6, "Update mit Fotos").
//
// The backend (CustomerMessageService) is the authority: photos only go out
// with a PHOTO_USE consent, an Art. 21 opt-out or a missing address means the
// update is handed over as PDF. These hints only explain that before sending.
import React from 'react';
import type {
  CustomerMessageContext,
  CustomerMessagePreview,
} from '../../api/customer-updates';

interface ComposerHintsProps {
  context: CustomerMessageContext | null;
  photosSelected: boolean;
  onRemovePhotos: () => void;
  disabled?: boolean;
}

export function ComposerHints({
  context,
  photosSelected,
  onRemovePhotos,
  disabled = false,
}: ComposerHintsProps) {
  if (!context) return null;
  const photoBlocked = photosSelected && !context.photo_consent;

  return (
    <div className="kundeninfo-hints">
      {!context.photo_consent && (
        <div
          className={`kundeninfo-hint ${photoBlocked ? 'kundeninfo-hint--blocking' : ''}`}
          role={photoBlocked ? 'alert' : 'status'}
        >
          <p>
            Keine Einwilligung „Fotonutzung“ erfasst. Fotos können nicht verschickt werden;
            ein Text-Update ist möglich. Die Einwilligung erfassen Sie im Kundenprofil.
          </p>
          {photoBlocked && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={onRemovePhotos}
              disabled={disabled}
            >
              Fotos entfernen
            </button>
          )}
        </div>
      )}
      {context.email_opt_out && (
        <p className="kundeninfo-hint" role="status">
          Kunde wünscht keine E-Mail-Updates. Die Kundeninfo wird als PDF zur Übergabe erstellt.
        </p>
      )}
      {!context.email_opt_out && !context.has_email && (
        <p className="kundeninfo-hint" role="status">
          Keine E-Mail-Adresse hinterlegt. Die Kundeninfo wird als PDF zur Übergabe erstellt.
        </p>
      )}
    </div>
  );
}

interface PreviewBoxProps {
  preview: CustomerMessagePreview;
  onClose: () => void;
}

export function MessagePreviewBox({ preview, onClose }: PreviewBoxProps) {
  return (
    <section className="kundeninfo-preview" aria-label="Vorschau der Kundeninfo">
      <div className="kundeninfo-preview-header">
        <h4>Vorschau{preview.delivery_method === 'pdf_manual' ? ' (PDF-Übergabe)' : ' (E-Mail)'}</h4>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
          Vorschau schließen
        </button>
      </div>
      {preview.blocked_reason && (
        <p className="kundeninfo-hint kundeninfo-hint--blocking" role="alert">
          {preview.blocked_reason}
        </p>
      )}
      <p className="kundeninfo-preview-subject">
        <strong>Betreff:</strong> {preview.subject}
      </p>
      <pre className="kundeninfo-preview-text">{preview.text}</pre>
      {preview.photo_count > 0 && (
        <p className="kundeninfo-preview-meta">
          {preview.photo_count === 1 ? '1 Foto' : `${preview.photo_count} Fotos`} als Anhang
        </p>
      )}
    </section>
  );
}
