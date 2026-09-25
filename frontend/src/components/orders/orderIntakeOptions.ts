// Order intake options (W2-06: DOM-05, DOM-06, DOM-09, DOM-04).
//
// One "Legierung & Farbe" picker sets both `metal_type` and `alloy`, so the
// two can no longer contradict each other. `order_type` drives the ring-size
// requirement (not a substring match on the title). Fassungsart codes match
// the backend `GemstoneSettingType` (and the ML encoder).
import type { MetalType } from '../../types';

export interface AlloyChoice {
  key: string;
  label: string;
  metal_type: MetalType;
  alloy: string;
}

export const ALLOY_CHOICES: readonly AlloyChoice[] = [
  { key: '999-gelb', label: '999 Feingold', metal_type: 'gold_24k', alloy: '999' },
  { key: '750-gelb', label: '750 Gelbgold', metal_type: 'gold_18k', alloy: '750' },
  { key: '750-weiss', label: '750 Weißgold', metal_type: 'white_gold_18k', alloy: '750' },
  { key: '750-rose', label: '750 Roségold', metal_type: 'rose_gold_18k', alloy: '750' },
  { key: '585-gelb', label: '585 Gelbgold', metal_type: 'gold_14k', alloy: '585' },
  { key: '585-weiss', label: '585 Weißgold', metal_type: 'white_gold_14k', alloy: '585' },
  { key: '585-rose', label: '585 Roségold', metal_type: 'rose_gold_14k', alloy: '585' },
  { key: '375-gelb', label: '375 Gelbgold', metal_type: 'gold_9k', alloy: '375' },
  { key: 'ag925', label: 'Silber 925 (Sterling)', metal_type: 'silver_925', alloy: 'Ag925' },
  { key: 'ag800', label: 'Silber 800', metal_type: 'silver_800', alloy: 'Ag800' },
  { key: 'pt950', label: 'Platin 950', metal_type: 'platinum_950', alloy: 'Pt950' },
  { key: 'pd950', label: 'Palladium 950', metal_type: 'palladium', alloy: 'Pd950' },
];

/** The picker entry for a stored order; '' when the pair is not a known combination. */
export function alloyChoiceKey(metalType?: string | null, alloy?: string | null): string {
  if (!metalType) return '';
  const normalizedAlloy = (alloy ?? '').toLowerCase();
  const exact = ALLOY_CHOICES.find(
    (c) => c.metal_type === metalType && c.alloy.toLowerCase() === normalizedAlloy
  );
  if (exact) return exact.key;
  if (normalizedAlloy) return '';
  return ALLOY_CHOICES.find((c) => c.metal_type === metalType)?.key ?? '';
}

export function findAlloyChoice(key: string): AlloyChoice | undefined {
  return ALLOY_CHOICES.find((c) => c.key === key);
}

export const ORDER_TYPE_OPTIONS: readonly { value: string; label: string }[] = [
  { value: 'ring', label: 'Ring' },
  { value: 'earrings', label: 'Ohrringe' },
  { value: 'chain', label: 'Kette' },
  { value: 'pendant', label: 'Anhänger' },
  { value: 'bracelet', label: 'Armband' },
  { value: 'brooch', label: 'Brosche' },
  { value: 'repair', label: 'Reparatur' },
  { value: 'custom', label: 'Sonstiges' },
];

export const SETTING_TYPE_OPTIONS: readonly { value: string; label: string }[] = [
  { value: 'bezel', label: 'Zargenfassung' },
  { value: 'prong', label: 'Krappenfassung' },
  { value: 'channel', label: 'Kanalfassung' },
  { value: 'pave', label: 'Pavé' },
  { value: 'tension', label: 'Spannfassung' },
  { value: 'invisible', label: 'Unsichtbare Fassung' },
];

export function settingTypeLabel(value?: string | null): string {
  if (!value) return '';
  return SETTING_TYPE_OPTIONS.find((o) => o.value === value)?.label ?? value;
}

interface DescribableStone {
  type: string;
  quantity?: number | null;
  carat?: number | null;
  color?: string | null;
  quality?: string | null;
  shape?: string | null;
  setting_type?: string | null;
  is_customer_stone?: boolean | null;
}

const CARAT = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** One German line per stone, e.g. "3 × Diamant 0,10 ct G/VS1, rund, Krappenfassung". */
export function describeGemstone(stone: DescribableStone): string {
  let head = `${stone.quantity ?? 1} × ${stone.type}`;
  if (stone.carat) head += ` ${CARAT.format(stone.carat)} ct`;
  const grade = [stone.color, stone.quality].filter(Boolean).join('/');
  if (grade) head += ` ${grade}`;
  const parts = [head];
  if (stone.shape) parts.push(stone.shape);
  if (stone.setting_type) parts.push(settingTypeLabel(stone.setting_type));
  if (stone.is_customer_stone) parts.push('Kundenstein');
  return parts.join(', ');
}
