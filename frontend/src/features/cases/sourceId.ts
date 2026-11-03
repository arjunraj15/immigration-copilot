export type SourceKind = "file" | "profile" | "note" | "message" | "event" | "unknown";

// What a source id points at. Files are bytes, everything else is a record on a case.
export function sourceKind(id: string): SourceKind {
  if (id.startsWith("UP-")) return "file";
  if (id.startsWith("PROFILE-")) return "profile";
  if (id.startsWith("Z-")) return "note";
  if (id.startsWith("MSG-")) return "message";
  if (id.startsWith("EV-")) return "event";
  return "unknown";
}

// The case a record id belongs to, such as PROFILE-CASE-0015-full_name or MSG-0015-2 giving CASE-0015.
export function caseIdFromSource(id: string): string | null {
  const match = /^(?:PROFILE-CASE-|Z-|MSG-|EV-)(\d{4})(?!\d)/.exec(id);
  return match ? `CASE-${match[1]}` : null;
}
