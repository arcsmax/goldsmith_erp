// KundeninfoTab tests — V1.2 Task 3.
//
// Pins:
//   (a) history renders returned updates newest-first with kind + status
//       badges.
//   (b) "Erstellen & senden" calls createUpdate then sendUpdate, and shows
//       the delivered-vs-PDF toast per the mocked send result (both
//       branches).
//   (c) "Als Entwurf speichern" calls createUpdate only — never sendUpdate.
//   (d) SMTP status: admin + unconfigured SMTP shows the amber note;
//       non-admin never calls getEmailConfig at all.
//   (e) VIEWER (hasRole → false) sees no compose form and listUpdates is
//       never called (the GET is 403 backend-side for that role).
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { CustomerUpdate } from '../../api/customer-updates';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockListUpdates = vi.fn();
const mockCreateUpdate = vi.fn();
const mockSendUpdate = vi.fn();
const mockMarkDelivered = vi.fn();
const mockDownloadUpdatePdf = vi.fn();
const mockGetMessageContext = vi.fn();
const mockPreviewUpdate = vi.fn();
const mockPreviewUpdatePdf = vi.fn();

vi.mock('../../api/customer-updates', () => ({
  customerUpdatesApi: {
    listUpdates: (...args: unknown[]) => mockListUpdates(...args),
    createUpdate: (...args: unknown[]) => mockCreateUpdate(...args),
    sendUpdate: (...args: unknown[]) => mockSendUpdate(...args),
    markDelivered: (...args: unknown[]) => mockMarkDelivered(...args),
    downloadUpdatePdf: (...args: unknown[]) => mockDownloadUpdatePdf(...args),
    getMessageContext: (...args: unknown[]) => mockGetMessageContext(...args),
    previewUpdate: (...args: unknown[]) => mockPreviewUpdate(...args),
    previewUpdatePdf: (...args: unknown[]) => mockPreviewUpdatePdf(...args),
  },
}));

const mockGetEmailConfig = vi.fn();
vi.mock('../../api/admin', () => ({
  getEmailConfig: (...args: unknown[]) => mockGetEmailConfig(...args),
}));

const mockLogError = vi.fn();
vi.mock('../../lib/logError', () => ({
  logError: (...args: unknown[]) => mockLogError(...args),
}));

const mockShowToast = vi.fn();
const mockUseAuth = vi.fn();
vi.mock('../../contexts', () => ({
  useAuth: () => mockUseAuth(),
  useToast: () => ({ showToast: mockShowToast }),
}));

vi.mock('./PhotoPicker', () => ({
  PhotoPicker: ({ selectedIds }: { selectedIds: string[] }) => (
    <div data-testid="photo-picker-stub">{selectedIds.length} Fotos ausgewählt</div>
  ),
}));

import { KundeninfoTab } from './KundeninfoTab';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeUpdate(overrides: Partial<CustomerUpdate> = {}): CustomerUpdate {
  return {
    id: 1,
    order_id: 1,
    repair_job_id: null,
    kind: 'progress',
    subject: 'Update',
    body: 'Body text',
    photo_ids: [],
    cost_change_request_id: null,
    token: 'tok-1',
    status: 'draft',
    sent_at: null,
    sent_by: 1,
    delivery_method: null,
    created_at: '2026-07-01T10:00:00Z',
    updated_at: '2026-07-01T10:00:00Z',
    ...overrides,
  };
}

function manageAuth(isAdmin = false) {
  return { hasRole: () => true, isAdmin };
}

function viewerAuth() {
  return { hasRole: () => false, isAdmin: false };
}

afterEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('KundeninfoTab', () => {
  it('renders update history newest-first with kind + status badges', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    mockListUpdates.mockResolvedValue([
      makeUpdate({
        id: 1,
        status: 'draft',
        subject: 'Älteres Update',
        created_at: '2026-06-01T10:00:00Z',
      }),
      makeUpdate({
        id: 2,
        status: 'sent',
        subject: 'Neueres Update',
        created_at: '2026-07-01T10:00:00Z',
        delivery_method: 'email',
      }),
    ]);

    render(<KundeninfoTab orderId={5} />);

    const items = await screen.findAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText('Neueres Update')).toBeInTheDocument();
    expect(within(items[0]).getByText('Gesendet')).toBeInTheDocument();
    expect(within(items[1]).getByText('Älteres Update')).toBeInTheDocument();
    expect(within(items[1]).getByText('Entwurf')).toBeInTheDocument();
    expect(mockListUpdates).toHaveBeenCalledWith(5);
  });

  it('"Erstellen & senden" calls createUpdate then sendUpdate and shows a success toast when delivered', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    mockListUpdates.mockResolvedValue([]);
    mockCreateUpdate.mockResolvedValue(makeUpdate({ id: 42, status: 'draft' }));
    mockSendUpdate.mockResolvedValue({
      update: makeUpdate({ id: 42, status: 'sent', delivery_method: 'email' }),
      delivered: true,
      method: 'email',
    });

    render(<KundeninfoTab orderId={7} />);
    await waitFor(() => expect(mockListUpdates).toHaveBeenCalledWith(7));

    await userEvent.type(screen.getByLabelText('Betreff'), 'Fortschritt Update');
    await userEvent.type(screen.getByLabelText('Nachricht'), 'Der Ring ist fast fertig.');
    await userEvent.click(screen.getByRole('button', { name: 'Erstellen & senden' }));

    await waitFor(() =>
      expect(mockCreateUpdate).toHaveBeenCalledWith(7, {
        kind: 'progress',
        subject: 'Fortschritt Update',
        body: 'Der Ring ist fast fertig.',
        photo_ids: [],
      })
    );
    expect(mockSendUpdate).toHaveBeenCalledWith(42);
    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith(expect.stringContaining('versendet'), 'success')
    );
  });

  it('"Erstellen & senden" shows the PDF-fallback toast and auto-downloads the PDF when the send result is not delivered', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    mockListUpdates.mockResolvedValue([]);
    mockCreateUpdate.mockResolvedValue(makeUpdate({ id: 43, status: 'draft' }));
    mockSendUpdate.mockResolvedValue({
      update: makeUpdate({ id: 43, status: 'sent', delivery_method: 'pdf_manual' }),
      delivered: false,
      method: 'pdf_manual',
    });
    mockDownloadUpdatePdf.mockResolvedValue(new Blob(['pdf-bytes'], { type: 'application/pdf' }));

    render(<KundeninfoTab orderId={7} />);
    await waitFor(() => expect(mockListUpdates).toHaveBeenCalledWith(7));

    await userEvent.click(screen.getByRole('button', { name: 'Erstellen & senden' }));

    await waitFor(() => expect(mockCreateUpdate).toHaveBeenCalled());
    expect(mockSendUpdate).toHaveBeenCalledWith(43);
    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith(expect.stringContaining('PDF'), 'info')
    );
    // Bug fix: SMTP-unconfigured sends must not feel like a no-op — the PDF
    // for the just-sent update is fetched and downloaded automatically.
    await waitFor(() => expect(mockDownloadUpdatePdf).toHaveBeenCalledWith(43));
  });

  it('"Als Entwurf speichern" calls createUpdate only — never sendUpdate', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    mockListUpdates.mockResolvedValue([]);
    mockCreateUpdate.mockResolvedValue(makeUpdate({ id: 44, status: 'draft' }));

    render(<KundeninfoTab orderId={9} />);
    await waitFor(() => expect(mockListUpdates).toHaveBeenCalledWith(9));

    await userEvent.click(screen.getByRole('button', { name: 'Als Entwurf speichern' }));

    await waitFor(() => expect(mockCreateUpdate).toHaveBeenCalledTimes(1));
    expect(mockSendUpdate).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith(expect.stringContaining('Entwurf'), 'success')
    );
  });

  it('shows the amber SMTP note for an admin when email is not configured', async () => {
    mockUseAuth.mockReturnValue(manageAuth(true));
    mockListUpdates.mockResolvedValue([]);
    mockGetEmailConfig.mockResolvedValue({
      smtp_host: null,
      smtp_port: 587,
      smtp_user: null,
      smtp_from: null,
      email_notifications_enabled: false,
      password_configured: false,
    });

    render(<KundeninfoTab orderId={3} />);

    expect(
      await screen.findByText('E-Mail nicht konfiguriert — Updates werden als PDF erzeugt')
    ).toBeInTheDocument();
    expect(mockGetEmailConfig).toHaveBeenCalledTimes(1);
  });

  it('never calls getEmailConfig for a non-admin manager', async () => {
    mockUseAuth.mockReturnValue(manageAuth(false));
    mockListUpdates.mockResolvedValue([]);

    render(<KundeninfoTab orderId={3} />);
    await waitFor(() => expect(mockListUpdates).toHaveBeenCalledWith(3));

    expect(mockGetEmailConfig).not.toHaveBeenCalled();
    expect(
      screen.queryByText('E-Mail nicht konfiguriert — Updates werden als PDF erzeugt')
    ).not.toBeInTheDocument();
  });

  it('never offers "Kostenänderung" (cost_change) as a compose option, but offers the others', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    mockListUpdates.mockResolvedValue([]);

    render(<KundeninfoTab orderId={3} />);
    await waitFor(() => expect(mockListUpdates).toHaveBeenCalledWith(3));

    const select = screen.getByLabelText('Art') as HTMLSelectElement;
    const optionValues = within(select)
      .getAllByRole('option')
      .map((option) => (option as HTMLOptionElement).value);

    expect(optionValues).not.toContain('cost_change');
    expect(optionValues).toEqual(
      expect.arrayContaining(['progress', 'ready_for_pickup', 'custom'])
    );
  });

  it('clicking "Senden" on a draft history row sends that update and shows the delivery toast', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    const draftUpdate = makeUpdate({ id: 77, status: 'draft' });
    mockListUpdates.mockResolvedValue([draftUpdate]);
    mockSendUpdate.mockResolvedValue({
      update: makeUpdate({ id: 77, status: 'sent', delivery_method: 'email' }),
      delivered: true,
      method: 'email',
    });

    render(<KundeninfoTab orderId={13} />);

    const item = (await screen.findAllByRole('listitem'))[0];
    await userEvent.click(within(item).getByRole('button', { name: 'Senden' }));

    await waitFor(() => expect(mockSendUpdate).toHaveBeenCalledWith(77));
    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith(expect.stringContaining('versendet'), 'success')
    );
  });

  it('hides the compose form and never calls listUpdates for a user without the manage role', () => {
    mockUseAuth.mockReturnValue(viewerAuth());

    render(<KundeninfoTab orderId={11} />);

    expect(screen.getByText(/Keine Berechtigung/)).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Erstellen & senden' })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Als Entwurf speichern' })
    ).not.toBeInTheDocument();
    expect(mockListUpdates).not.toHaveBeenCalled();
    expect(mockGetEmailConfig).not.toHaveBeenCalled();
  });

  // W2-08 / DOM-30: the "Fertiggestellt" milestone prompt pre-fills the
  // compose form; sending stays an explicit tap (consent per send).
  it('pre-fills the compose form from initialDraft without sending anything', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    mockListUpdates.mockResolvedValue([]);

    render(
      <KundeninfoTab
        orderId={14}
        initialDraft={{
          kind: 'ready_for_pickup',
          subject: 'Ihr Auftrag ist fertig',
          body: 'Guten Tag,',
          photoIds: ['p3', 'p2'],
        }}
      />
    );

    expect(await screen.findByLabelText('Betreff')).toHaveValue('Ihr Auftrag ist fertig');
    expect(screen.getByLabelText('Art')).toHaveValue('ready_for_pickup');
    expect(screen.getByLabelText('Nachricht')).toHaveValue('Guten Tag,');
    expect(screen.getByTestId('photo-picker-stub')).toHaveTextContent('2 Fotos ausgewählt');
    expect(mockCreateUpdate).not.toHaveBeenCalled();
    expect(mockSendUpdate).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// W6 "Update mit Fotos": consent hint, preview, PDF preview
// ---------------------------------------------------------------------------

function messageContext(overrides: Record<string, unknown> = {}) {
  return {
    customer_id: 3,
    has_email: true,
    photo_consent: false,
    email_opt_out: false,
    ...overrides,
  };
}

const PHOTO_DRAFT = {
  kind: 'progress' as const,
  subject: 'Zwischenstand',
  body: 'Der Stein ist gefasst.',
  photoIds: ['p1'],
};

describe('KundeninfoTab — W6 composer aids', () => {
  it('shows the consent hint and blocks sending photos without PHOTO_USE consent', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    mockListUpdates.mockResolvedValue([]);
    mockGetMessageContext.mockResolvedValue(messageContext());

    render(<KundeninfoTab orderId={21} initialDraft={PHOTO_DRAFT} />);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Keine Einwilligung „Fotonutzung“ erfasst'
    );
    expect(mockGetMessageContext).toHaveBeenCalledWith(21);
    expect(screen.getByRole('button', { name: 'Erstellen & senden' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Als Entwurf speichern' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Vorschau als PDF' })).toBeDisabled();
  });

  it('"Fotos entfernen" clears the photos so a text-only update can be sent', async () => {
    const user = userEvent.setup();
    mockUseAuth.mockReturnValue(manageAuth());
    mockListUpdates.mockResolvedValue([]);
    mockGetMessageContext.mockResolvedValue(messageContext());

    render(<KundeninfoTab orderId={22} initialDraft={PHOTO_DRAFT} />);

    await user.click(await screen.findByRole('button', { name: 'Fotos entfernen' }));

    expect(screen.getByTestId('photo-picker-stub')).toHaveTextContent('0 Fotos ausgewählt');
    expect(screen.getByRole('button', { name: 'Erstellen & senden' })).toBeEnabled();
    // The hint stays as information (role=status), no longer blocking.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('does not block photos when PHOTO_USE consent exists', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    mockListUpdates.mockResolvedValue([]);
    mockGetMessageContext.mockResolvedValue(messageContext({ photo_consent: true }));

    render(<KundeninfoTab orderId={23} initialDraft={PHOTO_DRAFT} />);

    await waitFor(() => expect(mockGetMessageContext).toHaveBeenCalled());
    expect(screen.queryByText(/Keine Einwilligung/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Erstellen & senden' })).toBeEnabled();
  });

  it('shows the opt-out hint when the customer objected to email updates', async () => {
    mockUseAuth.mockReturnValue(manageAuth());
    mockListUpdates.mockResolvedValue([]);
    mockGetMessageContext.mockResolvedValue(
      messageContext({ photo_consent: true, email_opt_out: true })
    );

    render(<KundeninfoTab orderId={24} />);

    expect(await screen.findByText(/Kunde wünscht keine E-Mail-Updates/)).toBeInTheDocument();
  });

  it('"Vorschau anzeigen" renders the email text returned by the backend', async () => {
    const user = userEvent.setup();
    mockUseAuth.mockReturnValue(manageAuth());
    mockListUpdates.mockResolvedValue([]);
    mockGetMessageContext.mockResolvedValue(messageContext({ photo_consent: true }));
    mockPreviewUpdate.mockResolvedValue({
      subject: 'Zwischenstand',
      text: 'Liebe/r Max Mustermann,\nDer Stein ist gefasst.\nDatenschutz: …',
      delivery_method: 'email',
      photo_count: 1,
      photo_consent: true,
      email_opt_out: false,
      has_email: true,
      legal_basis: 'Art. 6(1)(a) DSGVO (Einwilligung)',
      blocked_reason: null,
    });

    render(<KundeninfoTab orderId={25} initialDraft={PHOTO_DRAFT} />);

    await user.click(await screen.findByRole('button', { name: 'Vorschau anzeigen' }));

    const preview = await screen.findByRole('region', { name: 'Vorschau der Kundeninfo' });
    expect(within(preview).getByText(/Der Stein ist gefasst\./)).toBeInTheDocument();
    expect(within(preview).getByText('1 Foto als Anhang')).toBeInTheDocument();
    expect(mockPreviewUpdate).toHaveBeenCalledWith(25, {
      kind: 'progress',
      subject: 'Zwischenstand',
      body: 'Der Stein ist gefasst.',
      photo_ids: ['p1'],
    });
    expect(mockCreateUpdate).not.toHaveBeenCalled();
  });

  it('"Vorschau als PDF" downloads the unsaved content without creating an update', async () => {
    const user = userEvent.setup();
    mockUseAuth.mockReturnValue(manageAuth());
    mockListUpdates.mockResolvedValue([]);
    mockGetMessageContext.mockResolvedValue(messageContext({ has_email: false }));
    mockPreviewUpdatePdf.mockResolvedValue(new Blob(['%PDF'], { type: 'application/pdf' }));

    render(
      <KundeninfoTab
        orderId={26}
        initialDraft={{ ...PHOTO_DRAFT, photoIds: [] }}
      />
    );

    expect(await screen.findByText(/Keine E-Mail-Adresse hinterlegt/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Vorschau als PDF' }));

    await waitFor(() =>
      expect(mockPreviewUpdatePdf).toHaveBeenCalledWith(26, {
        kind: 'progress',
        subject: 'Zwischenstand',
        body: 'Der Stein ist gefasst.',
        photo_ids: [],
      })
    );
    expect(mockCreateUpdate).not.toHaveBeenCalled();
    expect(mockSendUpdate).not.toHaveBeenCalled();
  });

  it('shows the German 422 detail when the backend refuses the update', async () => {
    const user = userEvent.setup();
    mockUseAuth.mockReturnValue(manageAuth());
    mockListUpdates.mockResolvedValue([]);
    mockGetMessageContext.mockResolvedValue(messageContext({ photo_consent: true }));
    mockCreateUpdate.mockRejectedValue({
      response: { status: 422, data: { detail: 'Preise dürfen nur in Kostenvoranschlag …' } },
    });

    render(<KundeninfoTab orderId={27} initialDraft={{ ...PHOTO_DRAFT, photoIds: [] }} />);

    await user.click(await screen.findByRole('button', { name: 'Als Entwurf speichern' }));

    await waitFor(() =>
      expect(mockShowToast).toHaveBeenCalledWith(
        'Preise dürfen nur in Kostenvoranschlag …',
        'error'
      )
    );
  });
});
