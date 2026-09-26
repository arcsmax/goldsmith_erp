// Kunden-Import (CSV) (W4-03): upload Bestandskunden; duplicates by e-mail
// are skipped. Row errors show the row number and field only.
import React, { useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { downloadCustomerCsvTemplate, importCustomersCsv } from '../../api/admin';
import { queryKeys } from '../../api/queryKeys';
import { getErrorMessage } from '../../lib/errors';
import { logError } from '../../lib/logError';
import { Button, Card, Field } from '../../ui';

export const CustomerImportPanel: React.FC = () => {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);

  const upload = useMutation({
    mutationFn: (csv: File) => importCustomersCsv(csv),
    onSuccess: async () => {
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      await queryClient.invalidateQueries({ queryKey: queryKeys.customers.all });
    },
    onError: (err) => logError('CustomerImportPanel.import', err),
  });

  const result = upload.data;
  const hasErrors = (result?.error_count ?? 0) > 0;

  return (
    <Card title="Kunden-Import (CSV)" className="admin-panel">
      <p className="admin-panel__intro">
        Importieren Sie Bestandskunden aus einer CSV-Datei. Doppelte E-Mail-Adressen werden
        übersprungen. Pflichtfelder: <code>first_name</code>, <code>last_name</code>, <code>email</code>.
      </p>
      <div className="admin-form__inline">
        <Field label="CSV-Datei" name="customer_csv">
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv,text/plain"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              upload.reset();
            }}
          />
        </Field>
        <Button icon="inbox" loading={upload.isPending} disabled={!file} onClick={() => file && upload.mutate(file)}>
          Kunden importieren
        </Button>
        <Button variant="ghost" icon="file-text" onClick={downloadCustomerCsvTemplate}>
          Vorlage herunterladen
        </Button>
      </div>

      {upload.isError && (
        <p role="alert" className="admin-notice admin-notice--danger">
          {getErrorMessage(upload.error, 'Import fehlgeschlagen. Bitte Datei prüfen und erneut versuchen.')}
        </p>
      )}

      {result && (
        <div role="status" className={`admin-notice admin-notice--${hasErrors ? 'waiting' : 'done'}`}>
          <strong>
            {result.imported_count} importiert
            {result.skipped_count > 0 && `, ${result.skipped_count} übersprungen`}
            {hasErrors && `, ${result.error_count} Fehler`}
          </strong>
          {result.errors.length > 0 && (
            <ul className="admin-notice__list">
              {result.errors.map((e) => (
                <li key={`${e.row_number}-${e.field ?? ''}-${e.message}`}>
                  Zeile {e.row_number}
                  {e.field ? ` (${e.field})` : ''}: {e.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
};

export default CustomerImportPanel;
