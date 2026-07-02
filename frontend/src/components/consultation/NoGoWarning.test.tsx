// NoGoWarning tests — Task 9 (V1.1 consultation frontend).
//
// Pins:
//   (a) a conflict response renders one `.no-go-warning-banner` per
//       conflict with the No-Go value and matched_against source.
//   (b) an empty response renders nothing.
//   (c) an API error renders nothing and is logged via logError — never a
//       raw console.error (request/response bodies can carry allergy/no-go
//       text, see StyleNoGoStep's comment on the same rule).
//   (d) the check is skipped entirely without a customerId or without any
//       non-empty candidate.
//   (e) candidates are capped to 50 items / 200 chars each before the API
//       call, mirroring the backend's own limits so a runaway candidates
//       list never triggers a 422.
//
// Fake timers drive the 400ms debounce deterministically — see
// CustomerTypeahead.test.tsx for the same pattern and its userEvent caveat
// (avoided here entirely since this component takes no user input).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';

const mockCheckNoGoConflicts = vi.fn();
vi.mock('../../api/customers', () => ({
  customersApi: {
    checkNoGoConflicts: (...a: unknown[]) => mockCheckNoGoConflicts(...a),
  },
}));

const mockLogError = vi.fn();
vi.mock('../../lib/logError', () => ({
  logError: (...a: unknown[]) => mockLogError(...a),
}));

import { NoGoWarning } from './NoGoWarning';

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

async function advanceDebounce() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(400);
  });
}

describe('NoGoWarning', () => {
  it('renders a banner per conflict with the No-Go value and matched_against', async () => {
    mockCheckNoGoConflicts.mockResolvedValue([
      { no_go_id: 1, category: 'metal', value: 'Nickel', matched_against: 'Nickel' },
    ]);

    render(<NoGoWarning customerId={5} candidates={['Nickel']} />);
    await advanceDebounce();

    expect(mockCheckNoGoConflicts).toHaveBeenCalledWith(5, ['Nickel']);
    expect(screen.getByText('⚠️ No-Go der Kundin: Nickel (Nickel)')).toBeInTheDocument();
  });

  it('renders one banner per conflict when multiple conflicts are returned', async () => {
    mockCheckNoGoConflicts.mockResolvedValue([
      { no_go_id: 1, category: 'metal', value: 'Nickel', matched_against: 'Nickel' },
      { no_go_id: 2, category: 'stone', value: 'Opal', matched_against: 'Opal (Pech-Stein)' },
    ]);

    render(<NoGoWarning customerId={5} candidates={['Nickel', 'Opal']} />);
    await advanceDebounce();

    expect(screen.getByText('⚠️ No-Go der Kundin: Nickel (Nickel)')).toBeInTheDocument();
    expect(
      screen.getByText('⚠️ No-Go der Kundin: Opal (Opal (Pech-Stein))')
    ).toBeInTheDocument();
  });

  it('renders nothing when the API returns no conflicts', async () => {
    mockCheckNoGoConflicts.mockResolvedValue([]);

    const { container } = render(<NoGoWarning customerId={5} candidates={['Rotgold 585']} />);
    await advanceDebounce();

    expect(container.querySelector('.no-go-warning-banner')).toBeNull();
  });

  it('renders nothing and logs via logError (not console.error) when the API call fails', async () => {
    const apiError = new Error('network down');
    mockCheckNoGoConflicts.mockRejectedValue(apiError);

    const { container } = render(<NoGoWarning customerId={5} candidates={['Rotgold 585']} />);
    await advanceDebounce();

    expect(container.querySelector('.no-go-warning-banner')).toBeNull();
    expect(mockLogError).toHaveBeenCalledWith(expect.any(String), apiError);
  });

  it('skips the check entirely when customerId is missing', async () => {
    render(<NoGoWarning customerId={null} candidates={['Nickel']} />);
    await advanceDebounce();

    expect(mockCheckNoGoConflicts).not.toHaveBeenCalled();
  });

  it('skips the check when candidates are empty or whitespace-only', async () => {
    render(<NoGoWarning customerId={5} candidates={['', '   ']} />);
    await advanceDebounce();

    expect(mockCheckNoGoConflicts).not.toHaveBeenCalled();
  });

  it('caps candidates to 50 items and 200 chars each before calling the API', async () => {
    mockCheckNoGoConflicts.mockResolvedValue([]);
    const longValue = 'x'.repeat(250);
    const manyCandidates = Array.from({ length: 60 }, (_, i) => `c${i}`);

    render(<NoGoWarning customerId={5} candidates={[longValue, ...manyCandidates]} />);
    await advanceDebounce();

    expect(mockCheckNoGoConflicts).toHaveBeenCalledTimes(1);
    const [, sentCandidates] = mockCheckNoGoConflicts.mock.calls[0] as [number, string[]];
    expect(sentCandidates).toHaveLength(50);
    expect(sentCandidates[0]).toHaveLength(200);
  });
});
