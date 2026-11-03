import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { useRole } from "../lib/role";

// Frontend gate for the AI screens. Actor labels are demo controls, so this is a convenience and not security.
export default function RequireAdmin({ children }: { children: ReactNode }) {
  const { isAdmin } = useRole();
  if (isAdmin) return <>{children}</>;
  return (
    <main className="mx-auto max-w-xl p-8 text-center">
      <h1 className="text-xl font-semibold">Admin access needed</h1>
      <p className="mt-2 text-[var(--muted)]">
        AI prompt management is available when you act as Admin. Switch the Acting as menu in the top bar.
      </p>
      <Link to="/" className="mt-4 inline-block underline">
        Back to cases
      </Link>
    </main>
  );
}
