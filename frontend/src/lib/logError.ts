import axios from 'axios';

/** Log an error WITHOUT request/response bodies — they can carry PII
 *  (e.g. allergy no-go values in err.config.data / 422 echo payloads). */
export function logError(context: string, err: unknown): void {
  if (axios.isAxiosError(err)) {
    console.error(context, {
      status: err.response?.status ?? null,
      code: err.code ?? null,
      url: err.config?.url ?? null,
      message: err.message,
    });
    return;
  }
  console.error(context, err instanceof Error ? err.message : String(err));
}
