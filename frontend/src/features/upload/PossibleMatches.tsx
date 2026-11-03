import type { Match } from "./useIntake";

// Existing cases the server found for a similar client name. A name is not unique, so these are only candidates for a person to check.
export default function PossibleMatches({ matches }: { matches: Match[] }) {
  if (matches.length === 0) return null;
  return (
    <div className="mt-3 rounded-xl bg-[var(--warn-soft)] px-3 py-2 text-[var(--warn)]" role="alert">
      <b>POSSIBLE MATCH</b> A name is not unique. Is this one of these cases?
      <ul className="mt-1">
        {matches.map((item) => (
          <li key={item.case_id} className="flex items-center gap-3 py-0.5">
            <span className="font-mono font-bold">{item.case_id}</span>
            <span className="flex-1">{item.name}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
