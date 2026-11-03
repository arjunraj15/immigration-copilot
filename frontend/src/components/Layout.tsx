import { useCallback, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import DocumentDrawer from "../features/cases/DocumentDrawer";
import { DocViewerContext } from "../features/cases/docViewer";
import Icon, { type IconName } from "./Icon";
import { useRole } from "../lib/role";

// Top bar items in order. Cases also counts as active on an open case.
type NavItem = { to: string; label: string; icon: IconName; matches: (path: string) => boolean };
const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Cases", icon: "cases", matches: (path) => path === "/" || path.startsWith("/cases/") },
  { to: "/documents", label: "Documents", icon: "documents", matches: (path) => path.startsWith("/documents") },
  { to: "/exceptions", label: "Exceptions", icon: "exceptions", matches: (path) => path.startsWith("/exceptions") },
  { to: "/review", label: "Review", icon: "review", matches: (path) => path.startsWith("/review") },
  { to: "/status", label: "Status", icon: "status", matches: (path) => path.startsWith("/status") },
  { to: "/ai", label: "AI", icon: "ai", matches: (path) => path.startsWith("/ai") },
];

const NAV_LINK = "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm hover:bg-white/10";

function navClass(active: boolean): string {
  return `${NAV_LINK} ${active ? "bg-white/15 font-semibold" : "opacity-90"}`;
}

function ActingAsSelect() {
  const { actor, actors, changeActor } = useRole();
  const navigate = useNavigate();

  // A case from the old user may not be open to the new one, so go back to the new user's own queue.
  const switchActor = (next: string) => {
    changeActor(next);
    navigate("/");
  };

  return (
    <label className="flex items-center gap-2 rounded-xl bg-white/10 px-3 py-1.5 text-sm">
      <span className="opacity-80">Acting as</span>
      <select
        value={actor}
        onChange={(event) => switchActor(event.target.value)}
        className="rounded-md bg-white px-2 py-0.5 font-medium text-[#14213a]"
      >
        {actors.map((option) => (
          <option key={option.label} value={option.label}>
            {option.label} ({option.role === "OPS" ? "Operations" : "Legal"})
          </option>
        ))}
      </select>
    </label>
  );
}

// Top bar: brand, one link per page, AI (Admin only) and the Acting as switch. The acting role sets the accent color and the actor.
export default function Layout() {
  const { role } = useRole();
  const { pathname } = useLocation();
  const [openDoc, setOpenDoc] = useState<string | null>(null);
  const closeDoc = useCallback(() => setOpenDoc(null), []);

  useEffect(() => {
    document.documentElement.dataset.role = role;
  }, [role]);

  return (
    <DocViewerContext.Provider value={setOpenDoc}>
      <div className="min-h-screen">
        <header className="flex flex-wrap items-center gap-2 bg-[var(--header)] px-5 py-2.5 text-white">
          <Link to="/" className="mr-4 text-lg font-bold sm:text-xl">
            Immigration Case Co-Pilot
          </Link>
          <nav className="flex flex-wrap items-center gap-1" aria-label="Main">
            {NAV_ITEMS.map((item) => (
              <NavLink key={item.to} to={item.to} className={navClass(item.matches(pathname))}>
                <Icon name={item.icon} />
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto">
            <ActingAsSelect />
          </div>
        </header>
        <Outlet />
        <DocumentDrawer sourceId={openDoc} onClose={closeDoc} />
      </div>
    </DocViewerContext.Provider>
  );
}
