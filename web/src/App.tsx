import { useCallback, useEffect, useMemo, useState } from "react";
import { CoverageView } from "./components/Coverage";
import { OpsView } from "./components/Ops";
import { PaperView } from "./components/Paper";
import { SignalFeed } from "./components/SignalFeed";
import { loadBundle, vetoTop, type Bundle } from "./lib/data";

type Tab = "Sinyal" | "Paper Positions" | "Cakupan" | "Operasional";
const TABS: Tab[] = ["Sinyal", "Paper Positions", "Cakupan", "Operasional"];
type Mode = "filter" | "sniper";
const MODES: { id: Mode; label: string; desc: string }[] = [
  { id: "filter", label: "🛡️ Filter", desc: "validator aman · 60 mnt · SL15/TP30" },
  { id: "sniper", label: "⚡ Sniper", desc: "cepat · 1 mnt · SL6/TP15 · size kecil" },
];
const POLL_MS = 45_000;

function Metric({ label, value, note, tone, solid }: { label: string; value: string; note: string; tone?: string; solid?: string }) {
  return (
    <article className={solid ? `metric ${solid}` : "metric"}>
      <p className="metric-label mono">{label}</p>
      <p className="metric-value mono">{value}</p>
      <p className={tone ? `metric-note mono ${tone}` : "metric-note mono"}>{note}</p>
    </article>
  );
}

export default function App() {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [tab, setTab] = useState<Tab>("Sinyal");
  const [menuOpen, setMenuOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [failed, setFailed] = useState(false);
  const [mode, setMode] = useState<Mode>(() => {
    try {
      const saved = window.localStorage.getItem("mmp-mode");
      if (saved === "sniper" || saved === "filter") return saved;
    } catch {
      /* abaikan */
    }
    return "filter";
  });
  const [theme, setTheme] = useState<string>(() => {
    try {
      const saved = window.localStorage.getItem("mmp-theme");
      if (saved === "dark" || saved === "light") return saved;
      return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    } catch {
      return "light";
    }
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      window.localStorage.setItem("mmp-theme", theme);
    } catch {
      /* abaikan */
    }
  }, [theme]);

  useEffect(() => {
    try {
      window.localStorage.setItem("mmp-mode", mode);
    } catch {
      /* abaikan */
    }
  }, [mode]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const b = await loadBundle();
      setBundle(b);
      setFailed(!b.meta && b.signals.length === 0 && b.positions.length === 0);
    } finally {
      window.setTimeout(() => setRefreshing(false), 400);
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = window.setInterval(refresh, POLL_MS);
    return () => window.clearInterval(t);
  }, [refresh]);

  const m = useMemo(() => {
    if (!bundle) return null;
    const all = bundle.signals.filter((s) => (s.mode || "filter") === mode);
    const n = all.length;
    const avg = n ? all.reduce((a, s) => a + Number(s.confidence ?? 0), 0) / n : 0;
    const blind = n ? all.filter((s) => s.grade === "BLIND").length : 0;
    const mpos = bundle.positions.filter((p) => (p.mode || "filter") === mode);
    const closed = mpos.filter((p) => p.status === "CLOSED");
    const wins = closed.filter((p) => Number(p.pnl_pct ?? 0) > 0).length;
    const vt = vetoTop(all, 1)[0];
    const nPass = all.filter((s) => s.verdict === "PASS").length;
    return {
      n,
      signals: all,
      positions: mpos,
      avg: `${avg.toFixed(0)}%`,
      blindPct: n ? `${((blind / n) * 100).toFixed(1)}%` : "—",
      closedNote: closed.length ? `${wins}/${closed.length} win` : "belum ada CLOSED",
      vetoNote: vt ? `${vt.name} ×${vt.n}` : "belum ada veto",
      nPass,
      nOpen: mpos.filter((p) => p.status === "OPEN").length,
      nClosed: closed.length,
    };
  }, [bundle, mode]);

  return (
    <div className="page">
      <header className="topbar">
        <div className="wrap">
          <div className="topbar-row">
            <div className="brand">
              <div className="brand-mark">M</div>
              <div>
                <h1>Melok Melok Profit</h1>
                <p className="mono">Signal Intelligence · MMP Terminal</p>
              </div>
            </div>
            <div className="live">
              <div className="live-pill mono">
                <span className="dot" /> Live · <span>{bundle?.exportedAt ? new Date(bundle.exportedAt).toLocaleTimeString("id-ID") : "—"}</span>
              </div>
              <button
                type="button"
                className="btn"
                onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
                aria-label="Ganti mode malam/siang"
              >
                {theme === "dark" ? "☀️ Siang" : "🌙 Malam"}
              </button>
              <button type="button" className="btn active" onClick={refresh} aria-label="Refresh data">
                <span className={refreshing ? "spin" : ""}>↻</span> Refresh
              </button>
            </div>
            <button type="button" className="btn menu-btn" aria-label="Buka menu" onClick={() => setMenuOpen((v) => !v)}>
              {menuOpen ? "✕" : "☰"}
            </button>
          </div>
          <nav aria-label="Navigasi utama" className={menuOpen ? "nav mobile-open" : "nav"}>
            {TABS.map((t) => (
              <button key={t} type="button" className={tab === t ? "btn active" : "btn"} onClick={() => { setTab(t); setMenuOpen(false); }}>
                {t}
              </button>
            ))}
            <button
              type="button"
              className="btn"
              onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
              aria-label="Ganti mode malam/siang"
            >
              {theme === "dark" ? "☀️ Siang" : "🌙 Malam"}
            </button>
            <span className="nav-sync mono">Data per {bundle?.exportedAt ?? "—"} · refresh 45 dtk</span>
          </nav>
        </div>
      </header>

      <main className="main">
        <div className="wrap">
          {bundle?.ops?.killed ? (
            <div className="banner stop"><strong>STOP — Kill switch aktif.</strong> Scan &amp; alert dihentikan. Matikan via <span className="mono">python scripts/killswitch.py --off</span>.</div>
          ) : (
            <div className="banner ok">Status: <strong>RUNNING</strong> — kill switch tidak aktif.</div>
          )}

          {failed ? (
            <div className="empty" style={{ marginTop: 24 }}>
              <strong>Data web belum ada.</strong> Jalankan ekspor dulu:
              <code>python scripts/export_json.py</code>
            </div>
          ) : (
            <>
              <div className="mode-tabs" role="tablist" aria-label="Pilih mode">
                {MODES.map((md) => {
                  const c = bundle ? bundle.signals.filter((s) => (s.mode || "filter") === md.id).length : 0;
                  return (
                    <button
                      key={md.id}
                      type="button"
                      role="tab"
                      aria-selected={mode === md.id}
                      className={mode === md.id ? "mode-tab active" : "mode-tab"}
                      onClick={() => setMode(md.id)}
                    >
                      <strong>{md.label} · {c}</strong>
                      <small className="mono">{md.desc}</small>
                    </button>
                  );
                })}
              </div>
              <section aria-label="Ringkasan" className="metrics">
                <Metric label={mode === "sniper" ? "Sinyal sniper" : "Sinyal filter"} value={String(m?.n ?? "—")} note={`${m?.nPass ?? 0} PASS`} tone="text-mint" />
                <Metric label="Rata-rata confidence" value={m?.avg ?? "—"} note={m?.vetoNote ?? ""} solid="solid-rose" />
                <Metric label="Paper closed" value={String(m?.nClosed ?? 0)} note={m?.closedNote ?? ""} solid="solid-cyan" />
                <Metric label="Paper open" value={String(m?.nOpen ?? 0)} note={mode === "sniper" ? "max 3 · SL6/TP15" : "max 5 · SL15/TP30"} tone="text-rose" />
              </section>

              {tab === "Sinyal" && (
                <>
                  <div style={{ marginTop: 32 }}><SignalFeed signals={m?.signals ?? []} mode={mode} hideModeFilter /></div>
                  <div className="grid-12">
                    <div className="col-8"><PaperView positions={m?.positions ?? []} /></div>
                    <div className="col-4"><CoverageView batches={bundle?.batches ?? []} /></div>
                  </div>
                </>
              )}
              {tab === "Paper Positions" && <PaperView positions={m?.positions ?? []} expanded />}
              {tab === "Cakupan" && <CoverageView batches={bundle?.batches ?? []} expanded />}
              {tab === "Operasional" && <OpsView ops={bundle?.ops ?? null} meta={bundle?.meta ?? null} />}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
