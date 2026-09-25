// planGemstoneSync (W3-06): the diff between saved stones and form rows.
import { describe, expect, it } from 'vitest';
import { planGemstoneSync, isEmptyPlan } from './gemstoneSync';
import { EMPTY_GEMSTONE, toGemstoneRow } from './orderFormSchema';
import type { Gemstone } from '../../../api/gemstones';

const stone = {
  id: 1,
  order_id: 5,
  type: 'Diamant',
  quantity: 2,
  carat: 0.25,
  color: null,
  quality: null,
  shape: null,
  setting_type: null,
  is_customer_stone: false,
  cost: 99.5,
} as unknown as Gemstone;

describe('planGemstoneSync', () => {
  it('is empty when the rows equal the saved stones (comma decimals included)', () => {
    expect(isEmptyPlan(planGemstoneSync([stone], [toGemstoneRow(stone)], true))).toBe(true);
  });

  it('creates new rows, patches changed ones and removes dropped ones', () => {
    const other = { ...stone, id: 2, type: 'Saphir' } as Gemstone;
    const changed = { ...toGemstoneRow(stone), carat: '0,5' };
    const plan = planGemstoneSync([stone, other], [changed, { ...EMPTY_GEMSTONE, type: 'Opal', cost: '12,5' }], true);

    expect(plan.update).toEqual([{ id: 1, input: expect.objectContaining({ carat: 0.5 }) }]);
    expect(plan.create).toEqual([expect.objectContaining({ type: 'Opal', quantity: 1, cost: 12.5 })]);
    expect(plan.remove).toEqual([2]);
  });

  it('never sends a cost without cost rights or for a Kundenstein', () => {
    const row = { ...EMPTY_GEMSTONE, type: 'Perle', cost: '10' };
    expect(planGemstoneSync([], [row], false).create[0]).not.toHaveProperty('cost');
    expect(planGemstoneSync([], [{ ...row, is_customer_stone: true }], true).create[0]).not.toHaveProperty('cost');
  });
});
