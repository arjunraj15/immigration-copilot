// All API calls go through this wrapper. It adds the demo actor header the backend reads.
// Actor labels are demo controls, not authentication.
let actor = "OPS-01";

export function setActor(value: string): void {
  actor = value;
}

// Carries the code and message from the backend error body so screens can show them.
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public detail: unknown = null,
  ) {
    super(message);
  }
}

// A FormData body works as it is. The browser sets the multipart boundary, so no Content-Type is added here.
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { "X-Actor": actor, ...init.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, body?.error?.code ?? "HTTP_ERROR", body?.error?.message ?? `${response.status} ${response.statusText}`, body?.error ?? null);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

// A file download such as the approved form PDF. It needs the actor header, so a plain link cannot be used.
export async function apiBlob(path: string): Promise<Blob> {
  return (await apiFile(path)).blob;
}

// Same as apiBlob, plus the file name the server sent in Content-Disposition.
export async function apiFile(path: string): Promise<{ blob: Blob; fileName: string | null }> {
  const response = await fetch(`/api${path}`, { headers: { "X-Actor": actor } });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, body?.error?.code ?? "HTTP_ERROR", body?.error?.message ?? `${response.status} ${response.statusText}`);
  }
  const match = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") ?? "");
  return { blob: await response.blob(), fileName: match ? match[1] : null };
}
