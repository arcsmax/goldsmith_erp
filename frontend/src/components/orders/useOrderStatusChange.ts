// Status change for the order page (W2-08 DOM-18, W2-09 hallmark gate),
// on TanStack Query mutations (W4-03).
//
// PATCH /orders/{id}/status writes the answer straight into the order's
// cache entry (no refetch, no loading screen) and refreshes the Verlauf, the
// order lists and "Heute". A 409 "order.hallmark_required" opens the
// PunzierungsCheckModal, records the marks and retries the same change.
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ordersApi } from '../../api';
import apiClient from '../../api/client';
import { queryKeys } from '../../api/queryKeys';
import { useToast } from '../../contexts';
import { logError } from '../../lib/logError';
import { fireModal } from '../../lib/modal-stack';
import type { OrderStatus, OrderType } from '../../types';
import {
  PunzierungsCheckModal,
  type PunzierungsCheckModalProps,
  type PunzierungsCheckPayload,
} from '../qc/PunzierungsCheckModal';
import { needsReason, statusChangeErrorMessage, statusLabel } from './orderStatus';
import type { StatusChangeRequest } from './StatusChangeDialog';

const HALLMARK_CANCELLED =
  'Punzierungs-Check abgebrochen. Der Auftrag wurde nicht abgeschlossen.';

/**
 * True for the 409 the completion soft gate raises
 * (services/order_workflow.PunzierungRequiredError): the modern top-level
 * `code` first, the legacy nested `detail.code` as a fallback.
 */
export function isHallmarkRequiredError(err: unknown): boolean {
  const data = (
    err as { response?: { data?: { code?: unknown; detail?: { code?: unknown } } } }
  )?.response?.data;
  if (!data) return false;
  if (data.code === 'order.hallmark_required') return true;
  return (data.detail as { code?: unknown } | undefined)?.code === 'PUNZIERUNG_REQUIRED';
}

interface OrderRef {
  id: number;
  title: string;
  alloy?: string | null;
}

export interface OrderStatusChange {
  isBusy: boolean;
  /** Error of a change started from the header (shown under it). */
  headerError: string | null;
  /** Target of the open reason dialog (Pausiert / Storniert). */
  dialogTarget: OrderStatus | null;
  dialogError: string | null;
  request: (target: OrderStatus) => void;
  submit: (request: StatusChangeRequest) => Promise<void>;
  closeDialog: () => void;
}

export function useOrderStatusChange(order: OrderRef | undefined): OrderStatusChange {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [headerError, setHeaderError] = useState<string | null>(null);
  const [dialogTarget, setDialogTarget] = useState<OrderStatus | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);

  const change = useMutation({
    mutationFn: ({ id, request }: { id: number; request: StatusChangeRequest }) =>
      ordersApi.changeStatus(id, request),
    onSuccess: (updated: OrderType, { id }) => {
      queryClient.setQueryData(queryKeys.orders.detail(id), updated);
      void queryClient.invalidateQueries({ queryKey: queryKeys.orders.timeline(id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.orders.lists() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all });
    },
  });

  const recordHallmark = useMutation({
    mutationFn: ({ id, marks }: { id: number; marks: PunzierungsCheckPayload['marks'] }) =>
      apiClient.patch(`/orders/${id}`, { punzierung_verified_marks: marks }),
  });

  const report = (message: string, fromDialog: boolean) => {
    if (fromDialog) setDialogError(message);
    else setHeaderError(message);
  };

  const submit = async (request: StatusChangeRequest): Promise<void> => {
    if (!order) return;
    const fromDialog = dialogTarget !== null;
    setHeaderError(null);
    setDialogError(null);
    try {
      await change.mutateAsync({ id: order.id, request });
      setDialogTarget(null);
      showToast(`Status geändert: ${statusLabel(request.status)}`, 'success');
    } catch (err: unknown) {
      logError('OrderDetailPage.changeStatus', err);
      if (isHallmarkRequiredError(err)) {
        await handleHallmarkRequired(request, fromDialog);
        return;
      }
      report(statusChangeErrorMessage(err), fromDialog);
    }
  };

  /**
   * W2-09 (DOM-23): open the PunzierungsCheckModal prefilled with the
   * order's alloy, record the marks, then retry the same status change.
   */
  const handleHallmarkRequired = async (request: StatusChangeRequest, fromDialog: boolean) => {
    if (!order) return;
    let payload: PunzierungsCheckPayload;
    try {
      payload = await fireModal<PunzierungsCheckPayload, PunzierungsCheckModalProps>(
        PunzierungsCheckModal,
        { orderId: order.id, orderAlloy: order.alloy ?? undefined, orderTitle: order.title }
      );
    } catch {
      // Cancelled: say so, so "Weiter" does not silently do nothing.
      report(HALLMARK_CANCELLED, fromDialog);
      return;
    }
    try {
      await recordHallmark.mutateAsync({ id: order.id, marks: payload.marks });
    } catch (patchErr: unknown) {
      logError('OrderDetailPage.hallmarkPatch', patchErr);
      report(statusChangeErrorMessage(patchErr), fromDialog);
      return;
    }
    await submit(request);
  };

  const request = (target: OrderStatus) => {
    if (needsReason(target)) {
      setDialogError(null);
      setDialogTarget(target);
      return;
    }
    void submit({ status: target });
  };

  return {
    isBusy: change.isPending || recordHallmark.isPending,
    headerError,
    dialogTarget,
    dialogError,
    request,
    submit,
    closeDialog: () => setDialogTarget(null),
  };
}
