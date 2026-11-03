import { usDate, usDateTime } from "../../lib/dates";

// Display only. The backend does all date math. Both show US format, see lib/dates.ts.
export const formatLongDate = usDate;
export const formatStamp = usDateTime;

export function saveBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}

// crypto.randomUUID needs a secure page, so fall back to a random string on a plain http address.
export function newKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `key-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
