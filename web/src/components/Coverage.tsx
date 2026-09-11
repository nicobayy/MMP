import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Batch } from "../lib/data";

export function CoverageView({ batches, expanded }: { batches: Batch[]; expanded?: boolean }) {
  if (!batches.length) {
    return (
      <div className="empty">
        <strong>Belum ada batch_stats.</strong>
        <code>python scripts/run_scan.py --top-boosts --limit 5</code>
      </div>
    );
  }
  const tot = batches.reduce(
    (a, b) => ({ c: a.c + b.complete, p: a.p + b.partial, bl: a.bl + b.blind }),
    { c: 0, p: 0, bl: 0 }
  );
  const n = tot.c + tot.p + tot.bl || 1;
  const blindPct = Math.round((tot.bl / n) * 10) / 10;
  const rows = expanded ? batches : batches.slice(0, 5);

  return (
    <section style={expanded ? { marginTop: 32 } : undefined}>
      <div className="section-head">
        <div>
          <p className="section-kicker">Kualitas input</p>
          <h2 className="section-title">Cakupan</h2>
        </div>
      </div>
      <div className={expanded ? "cards cols-2" : "cards"}>
        <div className="card">
          <div className="donut-wrap">
            <div className="donut mono">{blindPct}<span style={{ fontSize: 11 }}>%</span></div>
            <div>
              <p className="mono" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.12em", opacity: 0.6 }}>BLIND share</p>
              <p style={{ margin: "4px 0 0", fontWeight: 700, fontSize: 14 }}>{tot.c} COMPLETE · {tot.p} PARTIAL · {tot.bl} BLIND</p>
              <p className="mono" style={{ fontSize: 11, marginTop: 8, color: blindPct > 50 ? "var(--rose)" : "var(--mint)" }}>
                {blindPct > 50 ? "● Bottleneck nyata: justifikasi sumber baru" : blindPct < 10 ? "● Cakupan sehat" : "● Zona abu-abu: lanjutkan pengukuran"}
              </p>
            </div>
          </div>
        </div>
        <div className="card">
          <p className="mono" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.12em", opacity: 0.6, margin: "0 0 12px" }}>
            {expanded ? "Riwayat batch" : "Batch terakhir"}
          </p>
          <div className="scroll-x">
            <table className="data mono">
              <thead><tr><th>ID</th><th>n</th><th>C</th><th>P</th><th>B</th></tr></thead>
              <tbody>
                {rows.map((b) => (
                  <tr key={b.id}><td>{b.id}</td><td>{b.n}</td><td>{b.complete}</td><td>{b.partial}</td><td>{b.blind}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          {expanded && batches.length > 1 && (
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={[...batches].reverse().map((b) => ({ id: b.id, blind: b.blind, partial: b.partial, complete: b.complete }))}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="id" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip />
                <Bar dataKey="complete" stackId="a" fill="var(--mint)" />
                <Bar dataKey="partial" stackId="a" fill="var(--cyan)" />
                <Bar dataKey="blind" stackId="a" fill="var(--rose)" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </section>
  );
}
