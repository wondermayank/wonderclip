
/** Shared layout for FAQ / Privacy / Terms: readable width, consistent typography. */
export function InfoPage({ title, intro, children, showUpdated = true }: {
  title: string; intro?: React.ReactNode; children: React.ReactNode; showUpdated?: boolean;
}) {
  return (
    <article className="mx-auto w-full max-w-3xl px-6 py-10 lg:px-10">
      <h1 className="text-3xl font-bold tracking-tight text-zinc-900 sm:text-4xl">{title}</h1>
      {showUpdated && <p className="mt-2 text-sm text-zinc-400">Last updated: {new Date().getFullYear()}</p>}
      {intro && <div className="mt-5 text-lg leading-relaxed text-zinc-600">{intro}</div>}
      <div className="mt-8 space-y-8 text-[15px] leading-relaxed text-zinc-700">{children}</div>
    </article>
  );
}

export function Section({ title, children, id }: { title: string; children: React.ReactNode; id?: string }) {
  return (
    <section id={id} className="scroll-mt-6">
      <h2 className="mb-3 text-xl font-bold tracking-tight text-zinc-900">{title}</h2>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

export function Bullets({ items }: { items: React.ReactNode[] }) {
  return (
    <ul className="list-disc space-y-1.5 pl-5 marker:text-violet-400">
      {items.map((it, i) => <li key={i}>{it}</li>)}
    </ul>
  );
}

export const A = ({ href, children }: { href: string; children: React.ReactNode }) => (
  <a href={href} target="_blank" rel="noopener noreferrer" className="font-medium text-violet-700 hover:underline">{children}</a>
);
