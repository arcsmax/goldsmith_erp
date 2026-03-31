/**
 * OfflineIndicator
 *
 * Shows a non-blocking banner at the top of the page when the workshop
 * device loses its WiFi connection, and a brief toast when the connection
 * comes back.  German UI text throughout — goldsmiths shouldn't have to
 * context-switch to English mid-job.
 *
 * Design notes (Jason):
 *  - Amber/gold offline banner so it reads clearly under workshop halogen
 *    lighting without being alarming (we use amber, not red).
 *  - Success toast is green-tinted, auto-dismisses after 4 s.
 *  - Both elements stay out of the critical content area — no modal, no
 *    overlay, no blocking interaction required.
 *  - Touch targets are not needed here; these are read-only indicators.
 */
import React, { useEffect, useState, useCallback } from 'react';

type ConnectionState = 'online' | 'offline' | 'restored';

export const OfflineIndicator: React.FC = () => {
  const [state, setState] = useState<ConnectionState>(
    navigator.onLine ? 'online' : 'offline'
  );

  const handleOffline = useCallback(() => {
    setState('offline');
  }, []);

  const handleOnline = useCallback(() => {
    setState('restored');
    // Auto-dismiss the "restored" toast after 4 seconds
    const timer = setTimeout(() => setState('online'), 4000);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    window.addEventListener('offline', handleOffline);
    window.addEventListener('online', handleOnline);
    return () => {
      window.removeEventListener('offline', handleOffline);
      window.removeEventListener('online', handleOnline);
    };
  }, [handleOffline, handleOnline]);

  if (state === 'online') return null;

  // ---- Offline banner --------------------------------------------------------
  if (state === 'offline') {
    return (
      <div
        role="status"
        aria-live="polite"
        aria-label="Offline-Modus aktiv"
        className={[
          // Layout
          'fixed top-0 inset-x-0 z-50',
          'flex items-center justify-center gap-2',
          'px-4 py-2',
          // Visuals — amber, not red; calm, not alarming
          'bg-amber-500/90 backdrop-blur-sm',
          'text-amber-950',
          'text-sm font-medium',
          // Shadow for visibility under all lighting conditions
          'shadow-md',
        ].join(' ')}
      >
        {/* Offline icon — simple circle with diagonal line, colorblind-safe
            because it also uses text */}
        <svg
          aria-hidden="true"
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="flex-shrink-0"
        >
          <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5"/>
          <line x1="2.5" y1="2.5" x2="13.5" y2="13.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
        </svg>
        <span>
          Offline-Modus —&nbsp;
          Daten werden synchronisiert, sobald die Verbindung wiederhergestellt ist
        </span>
      </div>
    );
  }

  // ---- "Restored" toast ------------------------------------------------------
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Verbindung wiederhergestellt"
      className={[
        // Layout — top banner, same position as offline banner
        'fixed top-0 inset-x-0 z-50',
        'flex items-center justify-center gap-2',
        'px-4 py-2',
        // Visuals — calm green, warm tint to stay on-brand
        'bg-emerald-600/90 backdrop-blur-sm',
        'text-emerald-50',
        'text-sm font-medium',
        'shadow-md',
        // Fade-in animation — subtle, non-distracting
        'animate-pulse',
      ].join(' ')}
    >
      <svg
        aria-hidden="true"
        width="16"
        height="16"
        viewBox="0 0 16 16"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="flex-shrink-0"
      >
        <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5"/>
        <polyline points="5,8.5 7,10.5 11,6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
      <span>Verbindung wiederhergestellt</span>
    </div>
  );
};

export default OfflineIndicator;
