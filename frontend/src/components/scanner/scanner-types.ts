// Minimal local mirror of @yudiel/react-qr-scanner's public types.
//
// We deliberately do NOT `import type` from the vendor module at the top level
// — that would pull the module into the main bundle and defeat the lazy split.
// TypeScript's `import type` is elided at build time, but some bundlers still
// trace it for tree-shaking decisions; keeping our own minimal mirror makes
// the lazy boundary explicit.
//
// Keep these shapes in sync with the vendor module's README:
// https://www.npmjs.com/package/@yudiel/react-qr-scanner

import type { CSSProperties, ReactNode } from 'react';

export interface IBoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface IPoint {
  x: number;
  y: number;
}

export interface IDetectedBarcode {
  boundingBox: IBoundingBox;
  cornerPoints: IPoint[];
  format: string;
  rawValue: string;
}

export type TrackFunction = (
  detectedCodes: IDetectedBarcode[],
  ctx: CanvasRenderingContext2D,
) => void;

export interface IScannerComponents {
  tracker?: TrackFunction;
  onOff?: boolean;
  torch?: boolean;
  zoom?: boolean;
  finder?: boolean;
  audio?: boolean;
}

export interface IScannerStyles {
  container?: CSSProperties;
  video?: CSSProperties;
  finderBorder?: number;
}

export interface IScannerClassNames {
  container?: string;
  video?: string;
}

export type BarcodeFormat =
  | 'aztec'
  | 'code_128'
  | 'code_39'
  | 'code_93'
  | 'codabar'
  | 'databar'
  | 'databar_expanded'
  | 'data_matrix'
  | 'dx_film_edge'
  | 'ean_13'
  | 'ean_8'
  | 'itf'
  | 'maxi_code'
  | 'micro_qr_code'
  | 'pdf417'
  | 'qr_code'
  | 'rm_qr_code'
  | 'upc_a'
  | 'upc_e'
  | 'linear_codes'
  | 'matrix_codes'
  | 'unknown';

export interface ScannerProps {
  onScan: (detectedCodes: IDetectedBarcode[]) => void;
  onError?: (error: unknown) => void;
  constraints?: MediaTrackConstraints;
  formats?: BarcodeFormat[];
  paused?: boolean;
  children?: ReactNode;
  components?: IScannerComponents;
  styles?: IScannerStyles;
  classNames?: IScannerClassNames;
  scanDelay?: number;
  allowMultiple?: boolean;
  sound?: boolean | string;
}
