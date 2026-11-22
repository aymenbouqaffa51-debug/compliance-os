async function getTrust(tenant: string, client: string) {
  const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  const res = await fetch(`${base}/api/trust/${tenant}/${client}`, { cache: 'no-store' });
  if (!res.ok) return null;
  return res.json();
}

export default async function TrustPage({
  params,
}: {
  params: { tenant: string; client: string };
}) {
  const data = await getTrust(params.tenant, params.client);

  if (!data) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-16">
        <h1 className="text-xl font-semibold">Not found</h1>
        <p className="mt-2 text-sm text-slate-400">
          This trust page does not exist or is not published.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-14">
      <div className="mb-8">
        <p className="text-xs uppercase tracking-widest text-accent">Security posture</p>
        <h1 className="mt-2 text-2xl font-semibold">{data.client.name}</h1>
        <p className="mt-1 text-sm text-slate-400">{data.client.sector}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {data.frameworks.map((f: any) => (
          <div key={f.framework_id} className="card">
            <div className="truncate text-xs uppercase tracking-wide text-slate-400">
              {f.framework}
            </div>
            <div className="mt-1 text-2xl font-semibold">{f.readiness_pct}%</div>
            <div className="mt-1 text-xs text-slate-500">{f.verdict}</div>
          </div>
        ))}
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        <div className="card">
          <div className="text-xs uppercase text-slate-400">Monitors passing</div>
          <div className="mt-1 text-xl font-semibold text-ok">{data.monitors.passing}</div>
        </div>
        <div className="card">
          <div className="text-xs uppercase text-slate-400">Monitors failing</div>
          <div className="mt-1 text-xl font-semibold text-bad">{data.monitors.failing}</div>
        </div>
        <div className="card">
          <div className="text-xs uppercase text-slate-400">EU data residency</div>
          <div className="mt-1 text-sm font-medium">{data.hosting.region}</div>
          <div className="text-xs text-slate-500">{data.hosting.country}</div>
        </div>
      </div>

      <div className="mt-4 card">
        <div className="text-xs uppercase text-slate-400">Where your data is processed</div>
        <p className="mt-2 text-sm text-slate-300">{data.hosting.note}</p>
        <p className="mt-2 text-xs text-slate-500">
          CNDP registration receipt on file: {data.cndp_receipt_on_file ? 'yes' : 'not published'}
        </p>
      </div>

      <p className="mt-8 border-t border-line pt-4 text-[11px] leading-relaxed text-slate-500">
        {data.disclaimer}
      </p>
    </main>
  );
}
