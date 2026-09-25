// Open the Annahmeschein PDF (W2-12) in a new tab for printing.
import { repairsApi } from '../../api/repairs';

/**
 * Opens the tab synchronously (inside the tap handler) so a tablet's popup
 * blocker allows it, then points it at the PDF blob. Without a tab (popup
 * blocked) the PDF is downloaded instead. Rejects when the PDF can't load.
 */
export async function openAnnahmeschein(repairId: number): Promise<void> {
  const win = window.open('', '_blank');
  try {
    const blob = await repairsApi.getAnnahmescheinPdf(repairId);
    const url = URL.createObjectURL(blob);
    if (win) {
      win.location.href = url;
      return;
    }
    const a = document.createElement('a');
    a.href = url;
    a.download = `Annahmeschein_${repairId}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    win?.close();
    throw err;
  }
}
