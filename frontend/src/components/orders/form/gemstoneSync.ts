// Saving the gemstone field array (W3-06). Stones live in their own table,
// so "Auftrag speichern" turns the rows into create / update / delete calls
// against /orders/{id}/gemstones: new rows are created, changed rows are
// patched and rows the user removed are deleted.
import { gemstonesApi, type Gemstone, type GemstoneCreateInput } from '../../../api/gemstones';
import { toGemstonePayload, toGemstoneRow, type GemstoneRow } from './orderFormSchema';

export interface GemstonePlan {
  create: GemstoneCreateInput[];
  update: { id: number; input: GemstoneCreateInput }[];
  remove: number[];
}

const same = (a: GemstoneCreateInput, b: GemstoneCreateInput): boolean =>
  JSON.stringify(a) === JSON.stringify(b);

/** Pure diff between the saved stones and the form rows. */
export function planGemstoneSync(
  saved: readonly Gemstone[],
  rows: readonly GemstoneRow[],
  canViewCost: boolean,
): GemstonePlan {
  const savedById = new Map(saved.map((stone) => [stone.id, stone]));
  const keptIds = new Set(rows.flatMap((row) => (row.gemstoneId === undefined ? [] : [row.gemstoneId])));

  const create = rows
    .filter((row) => row.gemstoneId === undefined)
    .map((row) => toGemstonePayload(row, canViewCost));

  const update = rows.flatMap((row) => {
    const stone = row.gemstoneId === undefined ? undefined : savedById.get(row.gemstoneId);
    if (!stone) return [];
    const input = toGemstonePayload(row, canViewCost);
    return same(input, toGemstonePayload(toGemstoneRow(stone), canViewCost)) ? [] : [{ id: stone.id, input }];
  });

  const remove = saved.filter((stone) => !keptIds.has(stone.id)).map((stone) => stone.id);
  return { create, update, remove };
}

export const isEmptyPlan = (plan: GemstonePlan): boolean =>
  plan.create.length + plan.update.length + plan.remove.length === 0;

/** Runs the plan; rejects on the first failed call. */
export async function applyGemstonePlan(orderId: number, plan: GemstonePlan): Promise<void> {
  await Promise.all([
    ...plan.create.map((input) => gemstonesApi.create(orderId, input)),
    ...plan.update.map(({ id, input }) => gemstonesApi.update(id, input)),
    ...plan.remove.map((id) => gemstonesApi.remove(id)),
  ]);
}
