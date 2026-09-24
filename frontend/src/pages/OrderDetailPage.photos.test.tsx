// OrderDetailPage — Fotos tab upload + scanner deep link (W2-01, FE-13,
// FE-04 deep-link part, DOM-01).
//
// DoD: from a tablet, scanner "Foto" opens the camera, the photo appears in
// the Fotos tab and can be ticked in Kundeninfo within 3 taps. These tests
// pin the page half: `?tab=fotos&capture=1` (and the legacy
// `?action=take-photo`) opens the Fotos tab and triggers the file picker;
// the upload control is GOLDSMITH/ADMIN only (DESIGN_VIEW).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import type { OrderType } from '../types';
import { triggerRefetch } from '../lib/refetchBus';

const mockGetById = vi.fn();
vi.mock('../api', () => ({
  ordersApi: { getById: (...a: unknown[]) => mockGetById(...a) },
  materialsApi: {},
}));

const mockGetForOrder = vi.fn();
const mockUpload = vi.fn();
vi.mock('../api/photos', async (orig) => {
  const actual = (await orig()) as Record<string, unknown>;
  return {
    ...actual,
    photosApi: {
      getForOrder: (...a: unknown[]) => mockGetForOrder(...a),
      upload: (...a: unknown[]) => mockUpload(...a),
    },
  };
});

const mockUseAuth = vi.fn();
vi.mock('../contexts', () => ({
  useToast: () => ({ showToast: vi.fn() }),
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

vi.mock('../components/orders/CostAlertBanner', () => ({
  CostAlertBanner: () => null,
}));
vi.mock('../components/orders/CustomerInfoCard', () => ({
  CustomerInfoCard: () => <div>customer-info</div>,
}));
// Thumbnails go through an authenticated fetch; render the requested src
// so the test can assert the URL without an HTTP mock.
vi.mock('../components/AuthenticatedImage', () => ({
  default: ({ src, alt }: { src: string; alt: string }) => (
    <img data-testid="auth-img" data-src={src} alt={alt} />
  ),
}));

import { OrderDetailPage } from './OrderDetailPage';

function makeOrder(): OrderType {
  return {
    id: 42,
    title: 'Ring mit Solitär',
    description: 'Solitärring',
    price: 1500,
    status: 'in_progress',
    customer_id: 1,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-02T00:00:00Z',
    materials: [],
  } as unknown as OrderType;
}

const EXISTING_PHOTO = {
  id: 'aaaa-1111',
  order_id: 42,
  file_path: '/srv/uploads/orders/42/a.jpg',
  notes: null,
  timestamp: '2026-09-02T10:00:00Z',
  taken_by: 1,
};

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.search}</div>;
}

function renderPage(entry = '/orders/42') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route
          path="/orders/:orderId"
          element={
            <>
              <OrderDetailPage />
              <LocationProbe />
            </>
          }
        />
      </Routes>
    </MemoryRouter>
  );
}

let clickSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  mockGetById.mockResolvedValue(makeOrder());
  mockGetForOrder.mockResolvedValue({ data: [EXISTING_PHOTO] });
  clickSpy = vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(() => {});
});

afterEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

describe('OrderDetailPage — Fotos tab upload', () => {
  it('shows the upload button on the Fotos tab for GOLDSMITH', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'GOLDSMITH' } });
    renderPage();

    await userEvent.click(await screen.findByText('Fotos (1)'));

    const input = await screen.findByLabelText('Foto aufnehmen');
    expect(input).toHaveAttribute('capture', 'environment');
    expect(clickSpy).not.toHaveBeenCalled();
  });

  it('renders existing photos through the authenticated thumbnail endpoint', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'GOLDSMITH' } });
    renderPage();

    await userEvent.click(await screen.findByText('Fotos (1)'));

    const img = await screen.findByTestId('auth-img');
    expect(img).toHaveAttribute('data-src', '/photos/aaaa-1111/thumbnail');
  });

  it('never renders the upload control or the picker for VIEWER, even via deep link', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'VIEWER' } });
    renderPage('/orders/42?tab=fotos&capture=1');

    expect(await screen.findAllByText('Ring mit Solitär')).not.toHaveLength(0);
    expect(screen.queryByLabelText('Foto aufnehmen')).not.toBeInTheDocument();
    expect(mockGetForOrder).not.toHaveBeenCalled();
    expect(clickSpy).not.toHaveBeenCalled();
  });

  it('uploads a selected file and adds it to the Fotos tab', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'ADMIN' } });
    mockUpload.mockResolvedValue({
      ...EXISTING_PHOTO,
      id: 'bbbb-2222',
      timestamp: '2026-09-03T10:00:00Z',
    });
    renderPage();
    await userEvent.click(await screen.findByText('Fotos (1)'));

    const file = new File(['x'], 'kamera.jpg', { type: 'image/jpeg' });
    await userEvent.upload(await screen.findByLabelText('Foto aufnehmen'), file);

    await waitFor(() =>
      expect(mockUpload).toHaveBeenCalledWith(42, file, expect.objectContaining({
        onProgress: expect.any(Function),
      }))
    );
    expect(await screen.findByText('Fotos (2)')).toBeInTheDocument();
    const srcs = (await screen.findAllByTestId('auth-img')).map((el) => el.getAttribute('data-src'));
    expect(srcs).toContain('/photos/bbbb-2222/thumbnail');
  });
});

describe('OrderDetailPage — realtime refresh (W2-13 hook)', () => {
  it('reloads the order and its photos when the orders topic fires, without unmounting the tab', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'GOLDSMITH' } });
    renderPage();
    await userEvent.click(await screen.findByText('Fotos (1)'));
    expect(mockGetById).toHaveBeenCalledTimes(1);

    mockGetForOrder.mockResolvedValue({
      data: [EXISTING_PHOTO, { ...EXISTING_PHOTO, id: 'cccc-3333' }],
    });
    triggerRefetch('orders');

    await waitFor(() => expect(mockGetById).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('Fotos (2)')).toBeInTheDocument();
    // Silent refresh: the Fotos tab (and a running upload) stays mounted.
    expect(screen.getByLabelText('Foto aufnehmen')).toBeInTheDocument();
  });
});

describe('OrderDetailPage — scanner deep link', () => {
  it('?tab=fotos&capture=1 opens the Fotos tab and triggers the picker once', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'GOLDSMITH' } });
    renderPage('/orders/42?tab=fotos&capture=1');

    expect(await screen.findByLabelText('Foto aufnehmen')).toBeInTheDocument();
    await waitFor(() => expect(clickSpy).toHaveBeenCalledTimes(1));
    // Params are consumed so a reload does not reopen the camera.
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(/^$/));
  });

  it('legacy ?action=take-photo behaves the same', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'GOLDSMITH' } });
    renderPage('/orders/42?action=take-photo');

    expect(await screen.findByLabelText('Foto aufnehmen')).toBeInTheDocument();
    await waitFor(() => expect(clickSpy).toHaveBeenCalledTimes(1));
  });

  it('?tab=fotos without capture opens the tab but not the picker', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'GOLDSMITH' } });
    renderPage('/orders/42?tab=fotos');

    expect(await screen.findByLabelText('Foto aufnehmen')).toBeInTheDocument();
    expect(clickSpy).not.toHaveBeenCalled();
  });

  it('?edit=status opens the Status tab', async () => {
    mockUseAuth.mockReturnValue({ user: { role: 'GOLDSMITH' } });
    renderPage('/orders/42?edit=status');

    expect(await screen.findByText('Status ändern')).toBeInTheDocument();
  });
});
