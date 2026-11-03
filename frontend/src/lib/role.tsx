import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { api, setActor } from "../api/client";

// Workspace view. Operations and Admin both use the paralegal view.
export type Role = "paralegal" | "attorney";
export type ActingAs = "operations" | "attorney" | "admin";
export type ActorOption = { label: string; role: "OPS" | "LEGAL"; case_count: number };

// Demo labels. Not authentication, the server checks every action.
const VIEW_FOR: Record<ActingAs, Role> = { operations: "paralegal", attorney: "attorney", admin: "paralegal" };
const STORAGE_KEY = "casedesk.actor";
const DEFAULT_ACTOR = "OPS-01";
// The demo has one Operations user and one Legal user. The other users stay in the data but are not offered.

type RoleState = {
  role: Role;
  acting: ActingAs;
  isAdmin: boolean;
  /** Every OPS and LEGAL user the server lists, for the Acting as picker. */
  actors: ActorOption[];
  changeActor: (label: string) => void;
  /** Label sent as X-Actor. */
  actor: string;
};

const RoleContext = createContext<RoleState | null>(null);

function actingFor(label: string): ActingAs {
  if (label.startsWith("LEGAL")) return "attorney";
  if (label.startsWith("ADMIN")) return "admin";
  return "operations";
}

function readStored(): string {
  try {
    return sessionStorage.getItem(STORAGE_KEY) || DEFAULT_ACTOR;
  } catch {
    return DEFAULT_ACTOR;
  }
}

export function RoleProvider({ children }: { children: ReactNode }) {
  const [chosen, setChosen] = useState<string>(readStored);
  const actorList = useQuery({ queryKey: ["actors"], queryFn: () => api<ActorOption[]>("/actors"), retry: false });

  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, chosen);
    } catch {
      // Storage can be blocked. The choice then lasts until reload.
    }
  }, [chosen]);

  if (actorList.isPending) return <p className="p-6">Loading...</p>;
  if (actorList.isError) return <p className="p-6" role="alert">Could not reach the server: {actorList.error.message}</p>;

  // A stored user the server no longer lists falls back to the first listed user.
  const actor = actorList.data.some((item) => item.label === chosen) ? chosen : (actorList.data[0]?.label ?? DEFAULT_ACTOR);
  const acting = actingFor(actor);
  // Set during render so the first queries of every child already carry the right user. Setting it again is harmless.
  setActor(actor);

  const value: RoleState = {
    role: VIEW_FOR[acting],
    acting,
    isAdmin: acting === "admin",
    actors: actorList.data,
    changeActor: setChosen,
    actor,
  };
  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
}

export function useRole(): RoleState {
  const value = useContext(RoleContext);
  if (!value) throw new Error("useRole must be used inside RoleProvider");
  return value;
}
