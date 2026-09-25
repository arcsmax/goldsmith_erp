// Open the repair Statusbericht PDF (W6, DOM section D Option 2) in a new
// tab. Mirrors annahmeschein.ts's popup-blocker-safe pattern exactly.
import { repairsApi } from '../../api/repairs';

/**
 * Opens the tab synchronously (inside the tap handler) so a tablet's popup
 * blocker allows it, then points it at the PDF blob. Without a tab (popup
 * blocked) the PDF is downloaded instead. Rejects when the PDF can't load.
 */
export async function openRepairStatusReport(repairId: number): Promise<void> {
  const win = window.open('', '_blank');
  try {
    const blob = await repairsApi.getStatusReportPdf(repairId);
    const url = URL.createObjectURL(blob);
    if (win) {
      win.location.href = url;
      return;
    }
    const a = document.createElement('a');
    a.href = url;
    a.download = `Statusbericht_Reparatur_${repairId}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    win?.close();
    throw err;
  }
}
