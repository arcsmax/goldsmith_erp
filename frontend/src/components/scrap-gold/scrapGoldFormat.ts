// Number formatting for the Altgold screens (W4-03).
const FINE_FORMATTER = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 3, maximumFractionDigits: 3 });
const WEIGHT_FORMATTER = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** Fine content with three decimals: "5,850 g". */
export function formatGrams(grams: number): string {
  return `${FINE_FORMATTER.format(grams)} g`;
}

/** Item weight with two decimals: "10,00 g". */
export function formatWeight(grams: number): string {
  return `${WEIGHT_FORMATTER.format(grams)} g`;
}

/** Accept "10,5" as well as "10.5". */
export function parseWeight(value: string): number {
  return parseFloat(value.replace(',', '.'));
}
