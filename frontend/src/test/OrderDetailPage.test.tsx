// OrderDetailPage regression tests.
//
// Scope:
//   * The "Angebot erstellen" button must NOT render the literal string
//     "F4DD" in front of its label. This was a CSS escape bug — content
//     was set to "F4DD" instead of the proper Unicode escape "\01F4DD"
//     for U+1F4DD (memo emoji), causing browsers to render the raw hex
//     characters next to the button label.
//   * We assert against the raw CSS source because JSDOM does not
//     compute ::before pseudo-element content; reading the file gives
//     us the only reliable signal.
//   * W2-08 (DOM-16, DOM-17, DOM-18, DOM-30): five tabs, the "Weiter"
//     button on PATCH /orders/{id}/status, the Verlauf timeline and the
//     milestone prompt after "Fertiggestellt".

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { useState } from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import type { OrderStatus, OrderType } from '../types';

describe('OrderDetailPage — "Angebot erstellen" button mojibake regression', () => {
  it('does not contain the literal string "F4DD" in the button CSS', () => {
    const cssPath = resolve(__dirname, '../styles/order-detail.css');
    const css = readFileSync(cssPath, 'utf-8');

    // Find the .btn-create-quote::before block.
    const blockMatch = css.match(/\.btn-create-quote::before\s*\{[^}]*\}/);
    expect(blockMatch).not.toBeNull();
    const block = blockMatch![0];

    // Must NOT contain bare "F4DD" (the mojibake symptom). The fixed
    // CSS uses the escape sequence \01F4DD which contains a backslash
    // before the F, so this regex still excludes the broken form.
    expect(block).not.toMatch(/"F4DD/);

    // Must NOT contain a stray SOH control char (U+0001) that snuck in
    // alongside the original broken escape.
    expect(block).not.toContain('\u0001');

    // Must contain a proper CSS Unicode escape that resolves to U+1F4DD
    // (memo emoji). Both \01F4DD and \1F4DD are valid CSS forms.
    expect(block).toMatch(/\\0?1F4DD/i);
  });
});

// ─── W2-08 ────────────────────────────────────────────────────────────────────

const mockGetById = vi.fn();
const mockChangeStatus = vi.fn();
const mockGetTimeline = vi.fn();
vi.mock('../api', () => ({
  ordersApi: {
    getById: (...a: unknown[]) => mockGetById(...a),
    changeStatus: (...a: unknown[]) => mockChangeStatus(...a),
    getTimeline: (...a: unknown[]) => mockGetTimeline(...a),
  },
  materialsApi: {},
}));

const mockGetForOrder = vi.fn();
vi.mock('../api/photos', async (orig) => {
  const actual = (await orig()) as Record<string, unknown>;
  return { ...actual, photosApi: { getForOrder: (...a: unknown[]) => mockGetForOrder(...a) } };
});

// W2-09: handleHallmarkRequired PATCHes punzierung_verified_marks via the
// raw apiClient (same call the scanner's ActionHandlers.ts makes) before
// retrying the status change.
const mockApiPatch = vi.fn();
vi.mock('../api/client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: (...a: unknown[]) => mockApiPatch(...a),
  },
}));

const mockShowToast = vi.fn();
const mockUseAuth = vi.fn();
vi.mock('../contexts', () => ({
  useToast: () => ({ showToast: mockShowToast }),
  useOrders: () => {
    const [tab, setTab] = useState('details');
    return {
      setActiveOrder: vi.fn(),
      setOrderTab: (_id: number, next: string) => setTab(next),
      getOrderTab: () => tab,
    };
  },
  useAuth: () => mockUseAuth(),
}));

// Children with their own data fetching are out of this test's focus.
vi.mock('../components/orders/CostAlertBanner', () => ({ CostAlertBanner: () => null }));
vi.mock('../components/orders/DeliveredActions', () => ({
  DeliveredActions: () => <div>abholprotokoll</div>,
}));
vi.mock('../components/orders/GemstoneList', () => ({ GemstoneList: () => <div>steine</div> }));
vi.mock('../components/orders/CustomerInfoCard', () => ({
  CustomerInfoCard: () => <div>customer-info</div>,
}));
vi.mock('../components/TimeTrackingTab', () => ({ default: () => <div>time-tracking</div> }));
vi.mock('../components/CommentsTab', () => ({ CommentsTab: () => <div>comments</div> }));
vi.mock('../components/scrap-gold', () => ({ ScrapGoldTab: () => <div>scrap-gold</div> }));
vi.mock('../components/orders/HandoffTab', () => ({ default: () => <div>handoff</div> }));
vi.mock('../components/orders/ArbeitszettelTab', () => ({ default: () => <div>arbeitszettel</div> }));
vi.mock('../components/orders/SollIstTab', () => ({ SollIstTab: () => <div>soll-ist</div> }));
vi.mock('../components/orders/CostBreakdownCard', () => ({
  CostBreakdownCard: () => <div>cost-breakdown</div>,
}));
vi.mock('../components/orders/CostChangeSection', () => ({
  CostChangeSection: () => <div>cost-change</div>,
}));
vi.mock('../components/orders/KundeninfoTab', () => ({
  KundeninfoTab: ({ initialDraft }: { initialDraft?: unknown }) => (
    <div data-testid="kundeninfo">{initialDraft ? JSON.stringify(initialDraft) : 'no-draft'}</div>
  ),
}));
vi.mock('../components/AuthenticatedImage', () => ({
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));

import { OrderDetailPage } from '../pages/OrderDetailPage';

function makeOrder(status: OrderStatus, overrides: Partial<OrderType> = {}): OrderType {
  return {
    id: 42,
    title: 'Trauringe Meier',
    description: 'Zwei Ringe, 585 Gelbgold',
    price: 1500,
    status,
    customer_id: 1,
    created_at: '2026-09-01T08:00:00Z',
    updated_at: '2026-09-02T08:00:00Z',
    materials: [],
    ...overrides,
  } as OrderType;
}

const PHOTOS = [
  { id: 'p1', order_id: 42, file_path: 'a.jpg', timestamp: '2026-09-01T10:00:00Z', taken_by: 1 },
  { id: 'p2', order_id: 42, file_path: 'b.jpg', timestamp: '2026-09-02T10:00:00Z', taken_by: 1 },
  { id: 'p3', order_id: 42, file_path: 'c.jpg', timestamp: '2026-09-03T10:00:00Z', taken_by: 1 },
  { id: 'p4', order_id: 42, file_path: 'd.jpg', timestamp: '2026-09-04T10:00:00Z', taken_by: 1 },
];

function renderPage(entry = '/orders/42') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/orders/:orderId" element={<OrderDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

function asRole(role: string) {
  mockUseAuth.mockReturnValue({ user: { role } });
}

beforeEach(() => {
  mockGetForOrder.mockResolvedValue({ data: PHOTOS });
  mockGetTimeline.mockResolvedValue({ order_id: 42, items: [] });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('OrderDetailPage — five tabs (DOM-17)', () => {
  it('renders exactly five tabs with role="tab" for GOLDSMITH', async () => {
    asRole('GOLDSMITH');
    mockGetById.mockResolvedValue(makeOrder('in_progress'));
    renderPage();

    const tablist = await screen.findByRole('tablist', { name: 'Auftragsbereiche' });
    const tabs = within(tablist).getAllByRole('tab');
    expect(tabs.map((t) => t.textContent?.replace(/\s*\(\d+\)$/, ''))).toEqual([
      'Übersicht',
      'Arbeit',
      'Fotos',
      'Kunde',
      'Verlauf',
    ]);
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true');
  });

  it('hides the Fotos tab for VIEWER (DESIGN_VIEW), leaving four tabs', async () => {
    asRole('VIEWER');
    mockGetById.mockResolvedValue(makeOrder('in_progress'));
    renderPage();

    const tablist = await screen.findByRole('tablist', { name: 'Auftragsbereiche' });
    const labels = within(tablist).getAllByRole('tab').map((t) => t.textContent);
    expect(labels).toEqual(['Übersicht', 'Arbeit', 'Kunde', 'Verlauf']);
    expect(mockGetForOrder).not.toHaveBeenCalled();
  });

  it('moves between tabs with the arrow keys', async () => {
    asRole('GOLDSMITH');
    mockGetById.mockResolvedValue(makeOrder('in_progress'));
    renderPage();

    const first = await screen.findByRole('tab', { name: 'Übersicht' });
    first.focus();
    await userEvent.keyboard('{ArrowRight}');
    expect(screen.getByRole('tab', { name: 'Arbeit' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel')).toHaveTextContent('time-tracking');
  });

  it('keeps the finance sections out of the Arbeit tab for VIEWER', async () => {
    asRole('VIEWER');
    mockGetById.mockResolvedValue(makeOrder('completed'));
    renderPage();

    await userEvent.click(await screen.findByRole('tab', { name: 'Arbeit' }));
    expect(screen.getByText('time-tracking')).toBeInTheDocument();
    expect(screen.queryByText('cost-breakdown')).not.toBeInTheDocument();
    expect(screen.queryByText('soll-ist')).not.toBeInTheDocument();
  });
});

describe('OrderDetailPage — "Angebot erstellen" role gate (LV2-04)', () => {
  it('shows "Angebot erstellen" for GOLDSMITH', async () => {
    asRole('GOLDSMITH');
    mockGetById.mockResolvedValue(makeOrder('in_progress'));
    renderPage();

    expect(await screen.findByRole('button', { name: 'Angebot erstellen' })).toBeInTheDocument();
  });

  it('hides "Angebot erstellen" for VIEWER — it used to navigate to /quotes and get silently bounced to /dashboard by the route guard', async () => {
    asRole('VIEWER');
    mockGetById.mockResolvedValue(makeOrder('in_progress'));
    renderPage();

    await screen.findAllByText('Trauringe Meier');
    expect(screen.queryByRole('button', { name: 'Angebot erstellen' })).not.toBeInTheDocument();
  });
});

describe('OrderDetailPage — Weiter button (DOM-18)', () => {
  it('labels the primary button with the next status and PATCHes it', async () => {
    asRole('GOLDSMITH');
    mockGetById.mockResolvedValue(makeOrder('waiting_for_fitting'));
    mockChangeStatus.mockResolvedValue(makeOrder('fitting_done'));
    renderPage();

    const weiter = await screen.findByRole('button', { name: 'Weiter: Anprobe abgeschlossen' });
    await userEvent.click(weiter);

    expect(mockChangeStatus).toHaveBeenCalledWith(42, { status: 'fitting_done' });
    expect(await screen.findByRole('button', { name: 'Weiter: In Bearbeitung' })).toBeInTheDocument();
    expect(mockShowToast).toHaveBeenCalledWith('Status geändert: Anprobe abgeschlossen', 'success');
  });

  it('offers only the allowed other transitions in the menu, cancel last', async () => {
    asRole('GOLDSMITH');
    mockGetById.mockResolvedValue(makeOrder('draft'));
    renderPage();

    await screen.findByRole('button', { name: 'Weiter: Bestätigt' });
    await userEvent.click(screen.getByRole('button', { name: 'Weitere Statuswechsel' }));
    const menu = screen.getByRole('menu');
    expect(within(menu).getAllByRole('menuitem').map((i) => i.textContent)).toEqual([
      'Storniert',
    ]);
  });

  it('shows no Weiter button for a delivered order and none for VIEWER', async () => {
    asRole('GOLDSMITH');
    mockGetById.mockResolvedValue(makeOrder('delivered'));
    const { unmount } = renderPage();
    await screen.findAllByText('Trauringe Meier');
    expect(screen.queryByRole('button', { name: /^Weiter:/ })).not.toBeInTheDocument();
    unmount();

    asRole('VIEWER');
    mockGetById.mockResolvedValue(makeOrder('in_progress'));
    renderPage();
    await screen.findAllByText('Trauringe Meier');
    expect(screen.queryByRole('button', { name: /^Weiter:/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Weitere Statuswechsel' })).not.toBeInTheDocument();
  });

  it('requires a reason before pausing and sends reason and resume date', async () => {
    asRole('GOLDSMITH');
    mockGetById.mockResolvedValue(makeOrder('in_progress'));
    mockChangeStatus.mockResolvedValue(makeOrder('on_hold'));
    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: 'Weitere Statuswechsel' }));
    await userEvent.click(screen.getByRole('menuitem', { name: 'Pausiert' }));

    const dialog = screen.getByRole('dialog', { name: 'Auftrag pausieren' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Auftrag pausieren' }));
    expect(mockChangeStatus).not.toHaveBeenCalled();
    expect(within(dialog).getByText(/Grund fehlt/)).toBeInTheDocument();

    await userEvent.type(within(dialog).getByLabelText(/Grund/), 'Kundin im Urlaub');
    await userEvent.type(within(dialog).getByLabelText(/Weiter am/), '2099-10-15');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Auftrag pausieren' }));

    expect(mockChangeStatus).toHaveBeenCalledWith(42, {
      status: 'on_hold',
      reason: 'Kundin im Urlaub',
      resume_date: '2099-10-15',
    });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('shows the backend German message on a 409', async () => {
    asRole('GOLDSMITH');
    mockGetById.mockResolvedValue(makeOrder('quality_check'));
    mockChangeStatus.mockRejectedValue({
      response: {
        status: 409,
        data: {
          detail: {
            code: 'INVALID_STATUS_TRANSITION',
            message: 'Statuswechsel von „Qualitätskontrolle“ nach „Fertiggestellt“ ist nicht erlaubt.',
            allowed: ['in_progress'],
          },
        },
      },
    });
    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: 'Weiter: Fertiggestellt' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Statuswechsel von „Qualitätskontrolle“ nach „Fertiggestellt“ ist nicht erlaubt.'
    );
  });

  it('opens the PunzierungsCheckModal on a hallmark-required 409 instead of a toast, and completes after recording a mark (W2-09)', async () => {
    asRole('GOLDSMITH');
    mockGetById.mockResolvedValue(makeOrder('quality_check', { alloy: '585' }));
    mockChangeStatus
      .mockRejectedValueOnce({
        response: {
          status: 409,
          data: {
            code: 'order.hallmark_required',
            extra: { order_id: 42, alloy: '585' },
            detail: {
              code: 'PUNZIERUNG_REQUIRED',
              order_id: 42,
              alloy: '585',
              message:
                'Vor Status „Fertiggestellt“ muss entweder die Feingehalts-Punze bestätigt oder ein Grund für „nicht punziert“ dokumentiert werden.',
            },
          },
        },
      })
      .mockResolvedValueOnce(makeOrder('completed', { alloy: '585' }));
    mockApiPatch.mockResolvedValue({ data: {} });
    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: 'Weiter: Fertiggestellt' }));

    // The modal opens instead of a raw error banner.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    const dialog = await screen.findByRole('dialog', { name: 'Punzierungs-Check' });
    await userEvent.click(
      within(dialog).getByTestId('punz-option-feingehalt_585').querySelector('input')!
    );
    await userEvent.click(within(dialog).getByTestId('punz-confirm'));

    await waitFor(() =>
      expect(mockApiPatch).toHaveBeenCalledWith('/orders/42', {
        punzierung_verified_marks: ['feingehalt_585'],
      })
    );
    await waitFor(() => expect(mockChangeStatus).toHaveBeenCalledTimes(2));
    expect(mockChangeStatus).toHaveBeenNthCalledWith(2, 42, { status: 'completed' });
    expect(mockShowToast).toHaveBeenCalledWith('Status geändert: Fertiggestellt', 'success');
  });

  it('shows a message instead of completing when the hallmark modal is cancelled (W2-09)', async () => {
    asRole('GOLDSMITH');
    mockGetById.mockResolvedValue(makeOrder('quality_check', { alloy: '585' }));
    mockChangeStatus.mockRejectedValue({
      response: {
        status: 409,
        data: { code: 'order.hallmark_required', detail: { code: 'PUNZIERUNG_REQUIRED' } },
      },
    });
    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: 'Weiter: Fertiggestellt' }));
    const dialog = await screen.findByRole('dialog', { name: 'Punzierungs-Check' });
    await userEvent.click(within(dialog).getByTestId('punz-cancel'));

    expect(await screen.findByRole('alert')).toHaveTextContent('Punzierungs-Check abgebrochen');
    expect(mockApiPatch).not.toHaveBeenCalled();
    expect(mockChangeStatus).toHaveBeenCalledTimes(1);
  });

  it('?edit=status opens the status menu on Übersicht', async () => {
    asRole('GOLDSMITH');
    mockGetById.mockResolvedValue(makeOrder('in_progress'));
    renderPage('/orders/42?edit=status');

    expect(await screen.findByRole('menu')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Übersicht' })).toHaveAttribute('aria-selected', 'true');
  });
});

describe('OrderDetailPage — Verlauf tab (DOM-16)', () => {
  it('renders the timeline newest first after one tap', async () => {
    asRole('GOLDSMITH');
    mockGetById.mockResolvedValue(makeOrder('in_progress'));
    mockGetTimeline.mockResolvedValue({
      order_id: 42,
      items: [
        { kind: 'status', id: 'event-1', at: '2026-09-01T08:00:00', summary: 'Angelegt: Entwurf', data: {} },
        { kind: 'photo', id: 'photo-p1', at: '2026-09-02T09:00:00', summary: 'Foto aufgenommen', data: {} },
      ],
    });
    renderPage();

    await userEvent.click(await screen.findByRole('tab', { name: 'Verlauf' }));
    const entries = await screen.findAllByRole('listitem');
    expect(entries.map((e) => e.getAttribute('data-kind'))).toEqual(['photo', 'status']);
    expect(mockGetTimeline).toHaveBeenCalledWith(42);
  });
});

describe('OrderDetailPage — milestone prompts (DOM-30)', () => {
  it('offers a prefilled Kundeninfo with the latest photos when the order becomes Fertiggestellt', async () => {
    asRole('GOLDSMITH');
    mockGetById.mockResolvedValue(makeOrder('quality_check'));
    mockChangeStatus.mockResolvedValue(makeOrder('completed'));
    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: 'Weiter: Fertiggestellt' }));

    const prompt = await screen.findByRole('region', { name: 'Kunde informieren?' });
    await userEvent.click(within(prompt).getByRole('button', { name: 'Kundeninfo vorbereiten' }));

    expect(screen.getByRole('tab', { name: 'Kunde' })).toHaveAttribute('aria-selected', 'true');
    const draft = JSON.parse(screen.getByTestId('kundeninfo').textContent ?? '{}');
    expect(draft.kind).toBe('ready_for_pickup');
    expect(draft.subject).toContain('Trauringe Meier');
    expect(draft.photoIds).toEqual(['p4', 'p3', 'p2']);
  });

  it('offers the handover step when the order becomes Ausgeliefert', async () => {
    asRole('GOLDSMITH');
    mockGetById.mockResolvedValue(makeOrder('completed'));
    mockChangeStatus.mockResolvedValue(makeOrder('delivered'));
    renderPage();

    await userEvent.click(await screen.findByRole('button', { name: 'Weiter: Ausgeliefert' }));

    const prompt = await screen.findByRole('region', { name: 'Übergabe dokumentieren?' });
    await userEvent.click(within(prompt).getByRole('button', { name: 'Übergabe öffnen' }));
    expect(screen.getByRole('tab', { name: 'Kunde' })).toHaveAttribute('aria-selected', 'true');
  });

  it('does not prompt on first load of an already completed order', async () => {
    asRole('GOLDSMITH');
    mockGetById.mockResolvedValue(makeOrder('completed'));
    renderPage();
    await screen.findByRole('button', { name: 'Weiter: Ausgeliefert' });
    expect(screen.queryByRole('region', { name: 'Kunde informieren?' })).not.toBeInTheDocument();
  });
});
