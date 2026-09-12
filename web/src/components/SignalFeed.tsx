import { useMemo, useState } from "react";
import { fmtPx, fmtUsd, fmtWhen, tierBadge, type Signal } from "../lib/data";

function confWidth(v: number): string {
  if (v >= 90) return "94%";
  if (v >= 85) return "88%";
  if (v >= 80) return "82%";
  if (v >= 70) return "72%";
  if (v >= 60) return "67%";
  if (v >= 50) return "54%";
  return "42%";
}

export function SignalFeed({ signals, mode: modeProp, hideModeFilter }: { signals: Signal[]; mode?: string; hideModeFilter?: boolean }) {
  const chains = useMemo(() => [...new Set(signals.map((s) => s.chain))].sort(), [signals]);
  const [query, setQuery] = useState("");
  const [verdict, setVerdict] = useState<"ALL" | "PASS" | "REJECT">("ALL");
  const [chain, setChain] = useState<string>("ALL");
  const [modeInner, setModeInner] = useState<"ALL" | "filter" | "sniper">("ALL");
  const mode = modeProp ?? modeInner;
  const [filtersOpen, setFiltersOpen] = useState(false);

  const filtered = useMemo(
    () =>
      signals.filter((s) => {
        if (verdict !== "ALL" && s.verdict !== verdict) return false;
        if (chain !== "ALL" && s.chain !== chain) return false;
        if (mode !== "ALL" && (s.mode || "filter") !== mode) return false;
        if (query) {
          const q = query.toLowerCase();
          const sym = `${s.symbol} ${s.chain} ${s.token} ${s.pair_addr}`.toLowerCase();
          if (!sym.includes(q)) return false;
        }
        return true;
      }),
    [signals, query, verdict, chain, mode]
  );

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const keyOf = (s: { id: number; mode?: string }) => `${s.mode || "filter"}-${s.id}`;
  const selected = filtered.find((s) => keyOf(s) === selectedId) ?? filtered[0] ?? signals[0];

  const downloadCsv = () => {
    const head = "id,ts,verdict,tier,confidence,symbol,chain,price,mcap,liq,grade,mode,reason";
    const esc = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const lines = filtered.map((s) =>
      [s.id, s.ts, s.verdict, s.tier, s.confidence, s.symbol, s.chain, s.price, s.mcap, s.liq, s.grade, s.mode || "filter", s.reason].map(esc).join(",")
    );
    const blob = new Blob([[head, ...lines].join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "mmp_signals.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  };

  if (!signals.length) {
    return (
      <div className="empty">
        <strong>Belum ada sinyal.</strong>
        <code>python scripts/run_scan.py --top-boosts --limit 10</code>
      </div>
    );
  }

  return (
    <div className="grid-12" style={{ marginTop: 0 }}>
      <section className="col-8">
        <div className="section-head">
          <div>
            <p className="section-kicker">Pemindai presisi</p>
            <h2 className="section-title">Feed Sinyal</h2>
          </div>
          <div className="filter-row">
            <button type="button" className="btn" onClick={() => setFiltersOpen((v) => !v)} aria-label="Buka filter">
              {filtersOpen ? "Tutup filter" : "Filter"}
            </button>
            <button type="button" className="btn" onClick={downloadCsv} aria-label="Unduh CSV">
              Unduh CSV
            </button>
          </div>
        </div>

        {filtersOpen && (
          <div className="filters">
            <label className="search-box">
              <span className="search-icon" aria-hidden>⌕</span>
              <span style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)" }}>Cari pair atau chain</span>
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Cari symbol / token / pair…" />
            </label>
            <div className="filter-row">
              {(["ALL", "PASS", "REJECT"] as const).map((v) => (
                <button key={v} type="button" className={verdict === v ? "btn active" : "btn"} onClick={() => setVerdict(v)}>
                  {v === "ALL" ? "Semua" : v}
                </button>
              ))}
              {!hideModeFilter && (["ALL", "filter", "sniper"] as const).map((v) => (
                <button key={v} type="button" className={mode === v ? "btn active" : "btn"} onClick={() => setModeInner(v)}>
                  {v === "ALL" ? "Filter+Sniper" : v === "filter" ? "Filter" : "Sniper"}
                </button>
              ))}
              <select
                value={chain}
                onChange={(e) => setChain(e.target.value)}
                className="btn"
                aria-label="Filter chain"
                style={{ textTransform: "none" }}
              >
                <option value="ALL">Semua chain</option>
                {chains.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>
        )}

        <div className="feed">
          <div className="feed-inner">
            <div className="feed-head">
              <span>Signal</span><span>Tier</span><span>Confidence</span><span>Entry</span><span>Grade</span>
              <span style={{ textAlign: "right" }}>ID</span>
            </div>
            {filtered.map((s) => {
              const w = fmtWhen(s.ts);
              return (
              <button
                type="button"
                key={`${s.mode || "filter"}-${s.id}`}
                onClick={() => setSelectedId(keyOf(s))}
                className={(selected && keyOf(selected) === keyOf(s) ? "feed-row selected" : "feed-row") + ((s.mode || "filter") === "sniper" ? " mode-sniper" : "")}
              >
                <span>
                  <strong className="feed-pair mono">{s.symbol || "?"} <span style={{ opacity: 0.5 }}>/ {s.dex ?? "?"}</span></strong>
                  <small className="feed-chain mono" title={w.full}>
                    {s.chain} · {((s.mode || "filter") === "sniper" ? "SNIPER" : "FILTER")} · {w.abs} ({w.rel})
                  </small>
                </span>
                <span className={s.verdict === "PASS" ? "tier-badge" : "tier-badge reject"}>{tierBadge(s.verdict, s.tier)}</span>
                <span className="conf-bar">
                  <span className="conf-track"><span className="conf-fill" style={{ width: confWidth(s.confidence) }} /></span>
                  <b className="mono">{s.confidence}</b>
                </span>
                <span className="mono" style={{ fontSize: 12 }}>{fmtPx(s.price)}</span>
                <span className="mono" style={{ fontWeight: 700 }}>{s.grade}</span>
                <span className="mono" style={{ textAlign: "right", fontSize: 12, opacity: 0.6 }}>#{s.id}</span>
              </button>
              );
            })}
            {filtered.length === 0 && <p className="empty-row mono">Tidak ada sinyal yang cocok.</p>}
          </div>
        </div>
        <p className="table-note mono">Menampilkan {filtered.length} dari {signals.length} · diurutkan terbaru</p>
      </section>

      <div className="col-4">{selected ? <Inspector s={selected} /> : null}</div>
    </div>
  );
}

export function Inspector({ s }: { s: Signal }) {
  const scores = Object.entries(s.scores ?? {});
  return (
    <aside className="inspector">
      <div className="inspector-top">
        <p className="kicker mono">Inspeksi Sinyal · #{s.id} · {fmtWhen(s.ts).abs} ({fmtWhen(s.ts).rel})</p>
        <div className="inspector-title">
          <h3>{s.symbol || "?"}</h3>
          <span className="verdict-badge mono">{s.verdict}{s.verdict === "PASS" ? ` · T${s.tier}` : ""} · {(s.mode || "filter") === "sniper" ? "SNIPER" : "FILTER"}</span>
        </div>
      </div>
      <div className="plan-grid">
        <div className="plan-cell"><p className="plan-label mono">Entry</p><p className="plan-value mono">{fmtPx(s.entry ?? s.price)}</p></div>
        <div className="plan-cell"><p className="plan-label mono">R:R</p><p className="plan-value mono">{s.rr ?? "—"}</p></div>
        <div className="plan-cell"><p className="plan-label mono">Target</p><p className="plan-value mono up">{fmtPx(s.tp)}</p></div>
        <div className="plan-cell"><p className="plan-label mono">Stop</p><p className="plan-value mono down">{fmtPx(s.sl)}</p></div>
      </div>
      <div className="inspector-sec">
        <div style={{ display: "flex", justifyContent: "space-between" }} className="mono">
          <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em", opacity: 0.6 }}>Confidence breakdown</span>
          <span style={{ fontSize: 10, fontWeight: 700 }}>{s.confidence}</span>
        </div>
        <div style={{ marginTop: 12 }}>
          {scores.map(([k, v]) => (
            <div className="score-row" key={k}>
              <div className="score-head mono"><span>{k}</span><span>{v}</span></div>
              <div className="score-track"><span className="score-fill" style={{ width: confWidth(Number(v)) }} /></div>
            </div>
          ))}
          {scores.length === 0 && <p className="mono" style={{ fontSize: 12 }}>Tidak ada skor.</p>}
        </div>
      </div>
      <div className="inspector-sec">
        <p className="mono" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.12em", opacity: 0.6 }}>Alasan keputusan</p>
        <p className="reason">{s.reason}</p>
        <div className="chip-row mono">
          <span className="chip">Liq {fmtUsd(s.liq)}</span>
          <span className="chip">MCap {fmtUsd(s.mcap)}</span>
          <span className="chip">Dual {s.dual_ok ? "OK" : "—"}</span>
        </div>
      </div>
      {s.vetoes.length > 0 && <p className="veto mono">Veto: {s.vetoes.slice(0, 4).join(" ; ")}</p>}
      {s.checklist.length > 0 && (
        <div className="inspector-sec">
          <p className="mono" style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.12em", opacity: 0.6 }}>Audit checklist</p>
          <table className="check-table mono" style={{ marginTop: 8 }}>
            <tbody>
              {s.checklist.map((c) => (
                <tr key={c.item}>
                  <td>{c.item}</td>
                  <td className={c.status === "OK" ? "st-ok" : c.status === "FAIL" ? "st-fail" : "st-warn"}>{c.status}</td>
                  <td style={{ opacity: 0.7 }}>{c.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {(s.size_usd !== null || s.url) && (
        <div className="inspector-sec mono" style={{ fontSize: 12 }}>
          {s.size_usd !== null && s.size_usd !== undefined && <p style={{ margin: "0 0 8px" }}>Size {fmtUsd(s.size_usd)}{s.risk_pct !== null ? ` · risk ${s.risk_pct}%` : ""}</p>}
          {s.url && <a href={s.url} target="_blank" rel="noreferrer">Buka DexScreener/GeckoTerminal ↗</a>}
        </div>
      )}
    </aside>
  );
}
