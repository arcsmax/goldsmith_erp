// Tests for the EstimatorPanel — the Kalkulation card surfaced in
// DRAFT quote editors for ADMIN/GOLDSMITH roles (V1.3 Phase 3).
//
// The panel is a state machine over 7 visible states; these tests
// cover the boundaries (role gate, DRAFT gate), the happy-path
// (fetch → override → accept), and the failure modes (insufficient
// data, network error, stale response).
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { EstimatorPanel } from "./EstimatorPanel";

// Mutable role flag so individual tests can flip hasRole().
let mockHasRoleReturn = true;
const mockShowToast = vi.fn();

vi.mock("../../api/estimates", () => ({
  estimatesApi: {
    getLaborEstimate: vi.fn(),
    getAccuracy: vi.fn(),
  },
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    hasRole: () => mockHasRoleReturn,
  }),
}));

vi.mock("../../contexts/ToastContext", () => ({
  useToast: () => ({ showToast: mockShowToast }),
}));

vi.mock("../../lib/logError", () => ({ logError: vi.fn() }));

import { estimatesApi } from "../../api/estimates";

const mockQuote = {
  id: 1,
  quote_number: "Q-001",
  status: "DRAFT",
  order_id: 10,
  customer_id: 5,
  created_by: 1,
  valid_until: "2026-12-31",
  approved_at: null,
  rejected_at: null,
  converted_at: null,
  subtotal: 0,
  tax_rate: 0,
  tax_amount: 0,
  total: 0,
  customer_signature_data: null,
  notes: null,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
  line_items: [],
};

const mockOrder = {
  id: 10,
  title: "Ring",
  description: "Test",
  price: null,
  status: "confirmed",
  customer_id: 5,
  deadline: null,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
  order_type: "ring",
  surface_finish: "polish",
  alloy: "gold_750",
};

const mockSuccessResponse = {
  hours_p50: 3.17,
  hours_p20: 2.37,
  hours_p80: 3.6,
  labor_cost_p50: 575.25,
  labor_cost_p20: 429.87,
  labor_cost_p80: 652.94,
  sample_size: 5,
  similarity_level: "workshop",
  similar_orders: [42, 57, 63, 71, 88],
  insufficient_data: false,
};

describe("EstimatorPanel", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockHasRoleReturn = true;
    mockShowToast.mockClear();
  });

  it("renders idle state with 'Schätzung holen' button", () => {
    render(
      <EstimatorPanel
        quote={mockQuote as any}
        order={mockOrder as any}
        onPatch={vi.fn()}
      />,
    );
    expect(screen.getByTestId("estimator-fetch-button")).toBeInTheDocument();
  });

  it("calls getLaborEstimate with the right request shape on click", async () => {
    vi.mocked(estimatesApi.getLaborEstimate).mockResolvedValue(
      mockSuccessResponse as any,
    );
    render(
      <EstimatorPanel
        quote={mockQuote as any}
        order={mockOrder as any}
        onPatch={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("estimator-fetch-button"));
    await waitFor(() => {
      expect(estimatesApi.getLaborEstimate).toHaveBeenCalledWith({
        order_type: "ring",
        finish_type: "polish", // prefilled from order.surface_finish
        has_stone_setting: false,
        alloy: "gold_750",
        complexity_rating: 3,
      });
    });
  });

  it("renders the EUR + hours result on success", async () => {
    vi.mocked(estimatesApi.getLaborEstimate).mockResolvedValue(
      mockSuccessResponse as any,
    );
    render(
      <EstimatorPanel
        quote={mockQuote as any}
        order={mockOrder as any}
        onPatch={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("estimator-fetch-button"));
    await waitFor(() => {
      expect(screen.getByTestId("estimator-cost")).toHaveTextContent(
        "575,25",
      );
      // formatHours(3.17 * 60 = 190.2 min, 1 dp) = "190,2"
      expect(screen.getByTestId("estimator-hours")).toHaveTextContent("3.2h");
    });
  });

  it("renders the insufficient-data notice when response.insufficient_data=true", async () => {
    vi.mocked(estimatesApi.getLaborEstimate).mockResolvedValue({
      ...mockSuccessResponse,
      insufficient_data: true,
      hours_p50: null,
      labor_cost_p50: null,
    } as any);
    render(
      <EstimatorPanel
        quote={mockQuote as any}
        order={mockOrder as any}
        onPatch={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("estimator-fetch-button"));
    await waitFor(() => {
      expect(screen.getByTestId("estimator-insufficient")).toBeInTheDocument();
      expect(
        screen.queryByTestId("estimator-accept-button"),
      ).not.toBeInTheDocument();
    });
  });

  it("updates the accept button label when override is dirty", async () => {
    vi.mocked(estimatesApi.getLaborEstimate).mockResolvedValue(
      mockSuccessResponse as any,
    );
    render(
      <EstimatorPanel
        quote={mockQuote as any}
        order={mockOrder as any}
        onPatch={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("estimator-fetch-button"));
    await waitFor(() => screen.getByTestId("estimator-accept-button"));
    fireEvent.change(screen.getByTestId("estimator-override-input"), {
      target: { value: "4" },
    });
    expect(screen.getByTestId("estimator-accept-button")).toHaveTextContent(
      "Mit 4 Stunden übernehmen",
    );
  });

  it("calls onPatch.addLineItem with estimator_metadata on accept", async () => {
    vi.mocked(estimatesApi.getLaborEstimate).mockResolvedValue(
      mockSuccessResponse as any,
    );
    const onPatch = vi.fn().mockResolvedValue(true);
    render(
      <EstimatorPanel
        quote={mockQuote as any}
        order={mockOrder as any}
        onPatch={onPatch}
      />,
    );
    fireEvent.click(screen.getByTestId("estimator-fetch-button"));
    await waitFor(() => screen.getByTestId("estimator-accept-button"));
    fireEvent.click(screen.getByTestId("estimator-accept-button"));
    await waitFor(() => {
      expect(onPatch).toHaveBeenCalledWith(
        expect.objectContaining({
          addLineItem: expect.objectContaining({
            line_type: "labor",
            quantity: 3.17,
            estimator_metadata: expect.objectContaining({
              suggested_hours: 3.17,
              quoted_hours: 3.17,
              similarity_level: "workshop",
              sample_size: 5,
              estimator_version: "labor_estimator_v1",
            }),
          }),
        }),
      );
    });
  });

  it("hides the panel for VIEWER role", () => {
    mockHasRoleReturn = false;
    const { container } = render(
      <EstimatorPanel
        quote={mockQuote as any}
        order={mockOrder as any}
        onPatch={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("hides the panel for non-DRAFT quote", () => {
    const sentQuote = { ...mockQuote, status: "SENT" };
    const { container } = render(
      <EstimatorPanel
        quote={sentQuote as any}
        order={mockOrder as any}
        onPatch={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows an error toast when the network call fails", async () => {
    vi.mocked(estimatesApi.getLaborEstimate).mockRejectedValue(
      new Error("Network error"),
    );
    render(
      <EstimatorPanel
        quote={mockQuote as any}
        order={mockOrder as any}
        onPatch={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("estimator-fetch-button"));
    await waitFor(() => {
      expect(mockShowToast).toHaveBeenCalledWith(
        expect.stringContaining("Schätzung"),
        "error",
      );
    });
    // After the error, the retry button is visible.
    expect(screen.getByTestId("estimator-retry-button")).toBeInTheDocument();
  });

  it("discards a stale response when quoteId changes mid-flight", async () => {
    let resolveFn: (v: any) => void = () => {};
    vi.mocked(estimatesApi.getLaborEstimate).mockReturnValue(
      new Promise((resolve) => {
        resolveFn = resolve;
      }) as any,
    );
    const { rerender } = render(
      <EstimatorPanel
        quote={mockQuote as any}
        order={mockOrder as any}
        onPatch={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId("estimator-fetch-button"));
    // User navigates to a different quote before the response lands.
    rerender(
      <EstimatorPanel
        quote={{ ...mockQuote, id: 2 } as any}
        order={mockOrder as any}
        onPatch={vi.fn()}
      />,
    );
    // Original request resolves — but panel is now bound to quote 2,
    // so the result must NOT render for the stale quote.
    resolveFn(mockSuccessResponse);
    await waitFor(() => {
      expect(screen.queryByTestId("estimator-cost")).not.toBeInTheDocument();
    });
  });
});