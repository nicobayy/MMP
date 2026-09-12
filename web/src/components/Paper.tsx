import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { equityCurve, fmtPx, fmtSigned, fmtWhen, tierStats, type Position } from "../lib/data";

export function PaperView({ positions, expanded }: { positions: Position[]; expanded?: boolean }) {
  const opens = positions.filter((p) => p.status === "OPEN");
  const closed = positions.filter((p) => p.status === "CLOSED");
  const wr = closed.length ? Math.round((closed.filter((p) => Number(p.pnl_pct ?? 0) > 0).length / closed.length) * 100) : 0;
  const eq = equityCurve(closed);
  const stats = tierStats(closed);

  if (!positions.length) {
    return (
      <div className="empty">
        <strong>Belum ada posisi paper.</strong>
        <code>python scripts/run_scan.py --top-boosts --limit 5 --chains solana,base --paper</code>
      </div>
    );
  }

  return (
    <section style={expanded ? { marginTop: 32 } : undefined}>
      <div className="section-head">
        <div>
          <p className="section-kicker">Simulasi tanpa risiko</p>
          <h2 className="section-title">Paper Positions</h2>
        </div>
        {expanded && <span className="mono" style={{ fontSize: 12 }}>{opens.length} open · {wr}% win-rate</span>}
      </div>

      <div className="cards cols-3">
        {opens.slice(0, expanded ? 9 : 3).map((p) => (
          <article className="card" key={`${p.mode || "filter"}-${p.id}`}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span className="mono" style={{ fontWeight: 700 }}>{p.symbol} <span style={{ opacity: 0.5 }}>/ {p.chain}</span></span>
              <span className="tier-badge">T{p.tier}·{((p.mode || "filter") === "sniper" ? "S" : "F")}</span>
            </div>
            <p className="pnl mono">OPEN</p>
            <p className="mono" style={{ fontSize: 11, opacity: 0.6 }}>entry {fmtPx(p.entry)} · #{p.id}</p>
            <p className="mono" style={{ fontSize: 11, opacity: 0.6 }}>buka {fmtWhen(p.opened_ts).abs} ({fmtWhen(p.opened_ts).rel})</p>
            <div className="pnl-bar" style={{ background: "var(--cyan)" }} />
          </article>
        ))}
        {closed.slice(0, expanded ? 0 : 0).map(() => null)}
        {closed.slice(0, expanded ? 9 : 0).map((p) => {
          const pos = Number(p.pnl_pct ?? 0) > 0;
          return (
            <article className="card" key={`${p.mode || "filter"}-${p.id}`}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="mono" style={{ fontWeight: 700 }}>{p.symbol} <span style={{ opacity: 0.5 }}>/ {p.chain}</span></span>
                <span className="tier-badge">T{p.tier}·{((p.mode || "filter") === "sniper" ? "S" : "F")}</span>
              </div>
              <p className={pos ? "pnl mono text-mint" : "pnl mono text-rose"}>{fmtSigned(p.pnl_pct)}</p>
              <p className="mono" style={{ fontSize: 11, opacity: 0.6 }}>{p.close_reason} · #{p.id}</p>
              <p className="mono" style={{ fontSize: 11, opacity: 0.6 }}>tutup {fmtWhen(p.closed_ts).abs} ({fmtWhen(p.closed_ts).rel})</p>
              <div className="pnl-bar" style={{ background: pos ? "var(--mint)" : "var(--rose)" }} />
            </article>
          );
        })}
      </div>

      {expanded && (
        <>
          <div className="chart-box">
            <h3 className="mono" style={{ margin: "0 0 4px", fontSize: 12, textTransform: "uppercase", letterSpacing: "0.12em" }}>
              Ekuitas modal-weighted (% modal)
            </h3>
            {eq.length ? (
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={eq}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="id" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Area type="monotone" dataKey="eq" stroke="var(--cyan)" fill="var(--cyan)" fillOpacity={0.25} name="eq_modal" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <p className="mono" style={{ fontSize: 12 }}>Belum ada CLOSED — kurva muncul setelah settle.</p>
            )}
          </div>

          <div className="chart-box">
            <h3 className="mono" style={{ margin: "0 0 12px", fontSize: 12, textTransform: "uppercase", letterSpacing: "0.12em" }}>Bukti per-tier</h3>
            <div className="scroll-x">
              <table className="data mono">
                <thead><tr><th>Tier</th><th>n</th><th>Win-rate</th><th>Expectancy</th><th>Max DD</th><th>Flag</th></tr></thead>
                <tbody>
                  {stats.map((s) => (
                    <tr key={s.tier}>
                      <td>T{s.tier}</td><td>{s.n}</td><td>{s.winrate}%</td>
                      <td>{s.expectancy}</td><td>{s.maxDd}</td><td>{s.flag}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="table-note mono">OK = n≥20 &amp; expectancy&gt;0. EXPLORATORY = n&lt;20.</p>
          </div>

          {closed.length > 0 && (
            <div className="chart-box">
              <h3 className="mono" style={{ margin: "0 0 4px", fontSize: 12, textTransform: "uppercase", letterSpacing: "0.12em" }}>PnL per posisi CLOSED</h3>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={closed.map((p) => ({ id: p.id, pnl: Number(p.pnl_pct ?? 0) }))}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="id" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Bar dataKey="pnl" fill="var(--rose)" name="pnl_pct" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}
    </section>
  );
}
