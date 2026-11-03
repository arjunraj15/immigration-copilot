// Temporary page body. Replace it with the real screen. Owner and plan section are shown on the page.
export default function Placeholder({ title, owner, note }: { title: string; owner: string; note: string }) {
  return (
    <section className="max-w-2xl space-y-2">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="text-sm text-[var(--muted)]">Owner: {owner}</p>
      <p>{note}</p>
    </section>
  );
}
