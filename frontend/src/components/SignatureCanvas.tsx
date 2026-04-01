// SignatureCanvas — touch-friendly HTML5 canvas signature pad
// Designed for workshop tablets: 44px minimum touch targets, works with gloves
import React, { useRef, useState, useEffect, useCallback } from 'react';

interface SignatureCanvasProps {
  onSave: (signatureBase64: string) => void;
  width?: number;
  height?: number;
}

interface Point {
  x: number;
  y: number;
}

export const SignatureCanvas: React.FC<SignatureCanvasProps> = ({
  onSave,
  width = 600,
  height = 200,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [isEmpty, setIsEmpty] = useState(true);
  const lastPoint = useRef<Point | null>(null);

  // Initialise the canvas context with ink-like stroke settings
  const initCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Fill with white so the exported PNG has a white background, not transparent
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.strokeStyle = '#1a1a2e';
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
  }, []);

  useEffect(() => {
    initCanvas();
  }, [initCanvas]);

  // Map a DOM client coordinate to canvas-local coordinates,
  // accounting for CSS scaling when the canvas is displayed smaller than its
  // internal resolution (e.g. on mobile viewports).
  const getCanvasPoint = (clientX: number, clientY: number): Point => {
    const canvas = canvasRef.current!;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    return {
      x: (clientX - rect.left) * scaleX,
      y: (clientY - rect.top) * scaleY,
    };
  };

  const startStroke = (point: Point) => {
    const ctx = canvasRef.current?.getContext('2d');
    if (!ctx) return;
    setIsDrawing(true);
    lastPoint.current = point;
    ctx.beginPath();
    ctx.arc(point.x, point.y, 1.25, 0, Math.PI * 2);
    ctx.fill();
  };

  const continueStroke = (point: Point) => {
    if (!isDrawing) return;
    const ctx = canvasRef.current?.getContext('2d');
    if (!ctx || !lastPoint.current) return;

    ctx.beginPath();
    ctx.moveTo(lastPoint.current.x, lastPoint.current.y);
    ctx.lineTo(point.x, point.y);
    ctx.stroke();
    lastPoint.current = point;
    setIsEmpty(false);
  };

  const endStroke = () => {
    setIsDrawing(false);
    lastPoint.current = null;
  };

  // ── Mouse handlers ──────────────────────────────────────────────────────────

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    startStroke(getCanvasPoint(e.clientX, e.clientY));
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isDrawing) return;
    e.preventDefault();
    continueStroke(getCanvasPoint(e.clientX, e.clientY));
  };

  const handleMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    endStroke();
  };

  const handleMouseLeave = () => {
    endStroke();
  };

  // ── Touch handlers (stylus / finger on tablet) ──────────────────────────────

  const handleTouchStart = (e: React.TouchEvent<HTMLCanvasElement>) => {
    e.preventDefault(); // prevents scroll-jank while signing
    const touch = e.touches[0];
    startStroke(getCanvasPoint(touch.clientX, touch.clientY));
  };

  const handleTouchMove = (e: React.TouchEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const touch = e.touches[0];
    continueStroke(getCanvasPoint(touch.clientX, touch.clientY));
  };

  const handleTouchEnd = (e: React.TouchEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    endStroke();
  };

  // ── Actions ─────────────────────────────────────────────────────────────────

  const handleClear = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = '#1a1a2e';
    setIsEmpty(true);
    lastPoint.current = null;
    setIsDrawing(false);
  };

  const handleSave = () => {
    const canvas = canvasRef.current;
    if (!canvas || isEmpty) return;
    const base64 = canvas.toDataURL('image/png');
    onSave(base64);
  };

  return (
    <div className="signature-canvas-wrapper">
      <p className="signature-canvas-hint">
        Bitte hier unterschreiben
      </p>

      <canvas
        ref={canvasRef}
        width={width}
        height={height}
        className="signature-canvas"
        aria-label="Unterschriftenfeld — bitte mit Finger oder Stift unterzeichnen"
        // Mouse
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
        // Touch
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      />

      <div className="signature-canvas-actions">
        {/* Löschen: min 44×44 px touch target (WCAG 2.1 AA, workshop-safe) */}
        <button
          type="button"
          className="btn-sig-clear"
          onClick={handleClear}
          aria-label="Unterschrift löschen und neu beginnen"
        >
          Löschen
        </button>

        <button
          type="button"
          className="btn-sig-save"
          onClick={handleSave}
          disabled={isEmpty}
          aria-label="Unterschrift bestätigen und speichern"
        >
          Unterschrift bestätigen
        </button>
      </div>
    </div>
  );
};
