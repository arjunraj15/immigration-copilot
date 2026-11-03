export type Picked = { file: File; path: string };
export type Rejected = { path: string; reason: string };

// Allowlist, not blocklist. Anything not listed here (exe, zip, scripts, html, macros and so on) never enters.
// Each type must also start with its own signature bytes, so an exe renamed to .pdf is refused.
const SIGNATURES: Record<string, number[][]> = {
  pdf: [[0x25, 0x50, 0x44, 0x46]],
  png: [[0x89, 0x50, 0x4e, 0x47]],
  jpg: [[0xff, 0xd8, 0xff]],
  jpeg: [[0xff, 0xd8, 0xff]],
  tif: [[0x49, 0x49, 0x2a, 0x00], [0x4d, 0x4d, 0x00, 0x2a]],
  tiff: [[0x49, 0x49, 0x2a, 0x00], [0x4d, 0x4d, 0x00, 0x2a]],
  docx: [[0x50, 0x4b, 0x03, 0x04]],
};
// Calls and messages as text. They have no signature bytes, so the head must be plain text with no NUL byte.
const TEXT_TYPES = ["txt", "eml", "vtt", "json"];

export const ACCEPT = [...Object.keys(SIGNATURES), ...TEXT_TYPES].map((ext) => `.${ext}`).join(",");
export const TYPE_HINT = "PDF, JPG, PNG, TIFF, DOCX, TXT, EML, VTT and JSON";
export const MAX_BYTES = 5 * 1024 * 1024;
export const MAX_FILES = 200;
// Stop walking a dropped folder after this many files so a huge folder cannot freeze the page.
const MAX_SCAN = 1000;

const JUNK_NAMES = new Set(["thumbs.db", "desktop.ini"]);

function extensionOf(path: string): string {
  const name = path.split("/").pop() ?? "";
  return name.includes(".") ? name.split(".").pop()!.toLowerCase() : "";
}

function isHiddenOrJunk(path: string): boolean {
  const parts = path.split("/");
  const name = parts[parts.length - 1].toLowerCase();
  return parts.some((part) => part.startsWith(".")) || name.startsWith("~$") || JUNK_NAMES.has(name);
}

// Returns the reason a file is refused, or null when it may be read. The backend must check again, this only keeps junk out of the screen.
export async function screenFile({ file, path }: Picked): Promise<string | null> {
  if (isHiddenOrJunk(path)) return "Hidden or system file";
  const ext = extensionOf(path);
  const signatures = SIGNATURES[ext];
  if (!signatures && !TEXT_TYPES.includes(ext)) return `Type not allowed. Use ${TYPE_HINT}`;
  if (file.size === 0) return "Empty file";
  if (file.size > MAX_BYTES) return `Larger than ${MAX_BYTES / 1024 / 1024} MB`;
  const head = new Uint8Array(await file.slice(0, 8).arrayBuffer());
  if (!signatures) return head.includes(0) ? "Content does not match the file type" : null;
  const matches = signatures.some((signature) => signature.every((byte, index) => head[index] === byte));
  return matches ? null : "Content does not match the file type";
}

export function fromFileList(files: FileList): Picked[] {
  return Array.from(files).map((file) => ({ file, path: file.webkitRelativePath || file.name }));
}

async function walk(entry: FileSystemEntry, out: Picked[]): Promise<void> {
  if (out.length >= MAX_SCAN) return;
  if (entry.isFile) {
    const file = await new Promise<File>((resolve, reject) => (entry as FileSystemFileEntry).file(resolve, reject));
    out.push({ file, path: entry.fullPath.replace(/^\//, "") });
    return;
  }
  // Skip hidden folders such as .git without opening them.
  if (entry.name.startsWith(".")) return;
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((resolve, reject) => reader.readEntries(resolve, reject));
    if (batch.length === 0) return;
    for (const child of batch) await walk(child, out);
  }
}

// Files and folders dropped on the page. Folders are opened recursively. Entries must be taken before the first await.
export async function collectDropped(transfer: DataTransfer): Promise<Picked[]> {
  const entries = Array.from(transfer.items)
    .map((item) => (item.kind === "file" ? item.webkitGetAsEntry() : null))
    .filter((entry): entry is FileSystemEntry => entry !== null);
  if (entries.length === 0) return fromFileList(transfer.files);
  const out: Picked[] = [];
  for (const entry of entries) await walk(entry, out);
  return out;
}
