import type { Meta, Ops } from "../lib/data";

export function OpsView({ ops, meta }: { ops: Ops | null; meta: Meta | null }) {
  if (!ops) {
    return (
      <div className="empty">
        <strong>Belum ada data ops.</strong>
        <code>python scripts/export_json.py</code>
      </div>
    );
  }
  const checks: { label: string; ok: boolean; detail: string }[] = [
    { label: "Database tersedia", ok: ops.n_total > 0, detail: `${ops.n_total} sinyal` },
    { label: "Scan scheduler aktif", ok: !!ops.last_scan, detail: ops.last_scan ?? "belum pernah" },
    { label: "Callout KOL tersedia", ok: ops.kol7 > 0, detail: `${ops.kol7} / 7 hari` },
    { label: "Whale feed segar (26 jam)", ok: ops.whale_26h > 0, detail: ops.whale_last ?? "belum pernah" },
    { label: "Paper settlement", ok: true, detail: `OPEN ${ops.n_open} / CLOSED ${ops.n_closed}` },
    { label: "Kill switch tidak aktif", ok: !ops.killed, detail: ops.killed ? "STOP aktif" : "running" },
  ];
  return (
    <section style={{ marginTop: 32 }}>
      <div className="section-head">
        <div>
          <p className="section-kicker">Status sistem</p>
          <h2 className="section-title">Operasional</h2>
        </div>
      </div>
      <div className="metrics" style={{ marginTop: 0 }}>
        <div className="metric"><p className="metric-label mono">Sinyal hari ini</p><p className="metric-value mono">{ops.n_today}</p><p className="metric-note mono">{ops.n_total} total</p></div>
        <div className="metric"><p className="metric-label mono">Paper open / closed</p><p className="metric-value mono">{ops.n_open} / {ops.n_closed}</p><p className="metric-note mono">Target ≥20 per tier</p></div>
        <div className="metric"><p className="metric-label mono">Whale 26 jam</p><p className="metric-value mono">{ops.whale_26h}</p><p className="metric-note mono">{ops.whale_last ?? "belum pernah"}</p></div>
        <div className="metric"><p className="metric-label mono">KOL 7 hari</p><p className="metric-value mono">{ops.kol7}</p><p className="metric-note mono">Threshold T1≥{meta?.t1 ?? 85} T2≥{meta?.t2 ?? 75}</p></div>
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <h3>Checklist sistem</h3>
        <ul className="check-list cols-2 mono">
          {checks.map((c) => (
            <li key={c.label}>
              <span className={c.ok ? "st-ok" : "st-warn"}>{c.ok ? "●" : "○"}</span> {c.label} — <span style={{ opacity: 0.6 }}>{c.detail}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <h3>Perintah cepat</h3>
        <p className="cmd mono">python scripts/run_scan.py --top-boosts --limit 5 --chains solana,base --paper{"\n"}python scripts/paper.py --settle --report{"\n"}python scripts/stats.py{"\n"}python scripts/report.py{"\n"}python scripts/ops_check.py</p>
      </div>
    </section>
  );
}
