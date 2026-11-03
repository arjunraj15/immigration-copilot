import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";

const CHECKS = ["", "/db", "/ocr", "/embeddings", "/ai"] as const;

type Health = { status: string };

function Check({ suffix }: { suffix: string }) {
  const { data, error, isLoading } = useQuery({
    queryKey: ["health", suffix],
    queryFn: () => api<Health>(`/health${suffix}`),
    retry: false,
  });
  const status = isLoading ? "checking" : error ? "error" : data?.status;
  const good = status === "ok";
  return (
    <li className="flex items-center justify-between rounded border border-[var(--line)] bg-[var(--surface)] px-4 py-2">
      <span className="font-mono text-sm">/api/health{suffix}</span>
      <span className="font-mono text-sm" style={{ color: good ? "var(--ok)" : "var(--bad)" }}>
        {status}
      </span>
    </li>
  );
}

export default function StatusPage() {
  return (
    <section className="max-w-xl space-y-4">
      <h1 className="text-2xl font-semibold">Status</h1>
      <p className="text-sm text-[var(--muted)]">
        Every line should read ok. The ai check reads no_key until ANTHROPIC_API_KEY is set in .env.
      </p>
      <ul className="space-y-2">
        {CHECKS.map((suffix) => (
          <Check key={suffix} suffix={suffix} />
        ))}
      </ul>
    </section>
  );
}
