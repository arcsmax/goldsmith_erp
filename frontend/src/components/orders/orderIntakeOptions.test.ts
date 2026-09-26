// orderIntakeOptions — silver 935 / palladium 500 additions.
//
// Source: fix-w2-09-hallmark.md open item #1; fix-w2-06-14-16-11.md open
// item #3. AlloyType (backend) cannot gain SILVER_935/PALLADIUM_500
// members without a Postgres enum migration (out of scope), but
// Order.alloy is a free string, so the "Legierung & Farbe" picker can
// offer these choices independently — this only proves the picker
// round-trips correctly, not that the backend enum understands them.
import { describe, expect, it } from 'vitest';
import { ALLOY_CHOICES, alloyChoiceKey, findAlloyChoice } from './orderIntakeOptions';

describe('ALLOY_CHOICES — silver 935 and palladium 500/950', () => {
  it('offers Silber 935', () => {
    const choice = ALLOY_CHOICES.find((c) => c.key === 'ag935');
    expect(choice).toEqual({
      key: 'ag935',
      label: 'Silber 935',
      metal_type: 'silver_925',
      alloy: 'Ag935',
    });
  });

  it('offers Palladium 500 alongside the existing Palladium 950', () => {
    expect(ALLOY_CHOICES.find((c) => c.key === 'pd950')?.alloy).toBe('Pd950');
    const pd500 = ALLOY_CHOICES.find((c) => c.key === 'pd500');
    expect(pd500).toEqual({
      key: 'pd500',
      label: 'Palladium 500',
      metal_type: 'palladium',
      alloy: 'Pd500',
    });
  });

  it('alloyChoiceKey resolves a stored (metal_type, alloy) pair back to the new keys', () => {
    expect(alloyChoiceKey('silver_925', 'Ag935')).toBe('ag935');
    expect(alloyChoiceKey('palladium', 'Pd500')).toBe('pd500');
    expect(alloyChoiceKey('palladium', 'Pd950')).toBe('pd950');
  });

  it('findAlloyChoice round-trips the new keys', () => {
    expect(findAlloyChoice('ag935')?.alloy).toBe('Ag935');
    expect(findAlloyChoice('pd500')?.alloy).toBe('Pd500');
  });
});
