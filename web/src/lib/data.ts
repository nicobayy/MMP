/* Kontrak data web/ <-> scripts/export_json.py. Satu-satunya sumber data UI. */

export type CheckItem = { item: string; status: string; detail: string };

export type Signal = {
  id: number;
  ts: string;
  verdict: string;
  tier: number;
  confidence: number;
  threshold: number | null;
  symbol: string;
  chain: string;
  token: string;
  pair_addr: string;
  price: number | null;
  dex: string | null;
  reason: string;
  vetoes: string[];
  scores: Record<string, number>;
  grade: string;
  dual_ok: boolean;
  dual_note: string;
  mcap: number | null;
  liq: number | null;
  url: string;
  entry: number | null;
  sl: number | null;
  tp: number | null;
  sl_pct: number | null;
  tp_pct: number | null;
  rr: number | null;
  size_usd: number | null;
  risk_pct: number | null;
  checklist: CheckItem[];
  mode: string;
};

export type Position = {
  id: number;
  signal_id: number;
  symbol: string;
  chain: string;
  token: string;
  pair_addr: string;
  entry: number | null;
  sl: number | null;
  tp: number | null;
  risk_pct: number | null;
  tier: number;
  status: string;
  opened_ts: string | null;
  closed_ts: string | null;
  exit_price: number | null;
  pnl_pct: number | null;
  close_reason: string;
  mode: string;
};

export type Batch = {
  id: number;
  ts: string;
  n: number;
  complete: number;
  partial: number;
  blind: number;
  hp_ok: number;
  hp_no_tax: number;
  hp_fail: number;
};

export type Ops = {
  exported_at: string;
  last_scan: string | null;
  n_today: number;
  n_total: number;
  whale_last: string | null;
  whale_26h: number;
  n_open: number;
  n_closed: number;
  kol7: number;
  killed: boolean;
  db_size: number;
};

export type Meta = {
  exported_at: string;
  t1: number;
  t2: number;
  n_signals: number;
  n_pass: number;
  n_open: number;
  n_closed: number;
};

async function get<T>(path: string): Promise<T | null> {
  try {
    const r = await fetch(path, { cache: "no-store" });
    if (!r.ok) return null;
    return (await r.json()) as T;
  } catch {
    return null;
  }
}

export type Bundle = {
  meta: Meta | null;
  signals: Signal[];
  positions: Position[];
  batches: Batch[];
  ops: Ops | null;
  exportedAt: string | null;
};

export async function loadBundle(): Promise<Bundle> {
  const [meta, sig, pap, bat, ops] = await Promise.all([
    get<Meta>("data/meta.json"),
    get<{ exported_at: string; signals: Signal[] }>("data/signals.json"),
    get<{ exported_at: string; positions: Position[] }>("data/paper.json"),
    get<{ exported_at: string; batches: Batch[] }>("data/batches.json"),
    get<Ops>("data/ops.json"),
  ]);
  const signals = (sig?.signals ?? []).map((s) => ({ ...s, mode: s.mode || "filter" }));
  const positions = (pap?.positions ?? []).map((p) => ({ ...p, mode: p.mode || "filter" }));
  return {
    meta,
    signals,
    positions,
    batches: bat?.batches ?? [],
    ops,
    exportedAt: meta?.exported_at ?? sig?.exported_at ?? null,
  };
}

/* ---------- format ---------- */

export function fmtUsd(x: unknown): string {
  if (x === null || x === undefined || (x as string) === "") return "—";
  const v = Number(x);
  if (!isFinite(v)) return "—";
  if (Math.abs(v) >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
  if (Math.abs(v) >= 1_000) return `$${(v / 1_000).toFixed(1)}K`;
  return `$${v.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
}

export function fmtPx(x: number | null | undefined): string {
  if (x === null || x === undefined) return "—";
  const v = Number(x);
  if (!isFinite(v) || v === 0) return "—";
  if (v < 0.01) return `$${v.toFixed(6)}`;
  if (v < 1) return `$${v.toFixed(4)}`;
  return `$${v.toLocaleString("en-US", { maximumFractionDigits: 4 })}`;
}

export function fmtSigned(x: number | null | undefined): string {
  if (x === null || x === undefined) return "—";
  const v = Number(x);
  if (!isFinite(v)) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}

export function tierBadge(verdict: string, tier: number): string {
  if (verdict === "PASS" && tier === 1) return "T1";
  if (verdict === "PASS") return "T2";
  return "REJECT";
}

/* ---------- analitik (cermin logika Python, baca saja) ---------- */

export type EquityPoint = { id: number; symbol: string; eq: number; dd: number; pnl: number };

export function equityCurve(closed: Position[]): EquityPoint[] {
  const rows = [...closed].sort((a, b) => a.id - b.id);
  let eq = 0;
  let peak = 0;
  return rows.map((r) => {
    const pnl = Number(r.pnl_pct ?? 0);
    const risk = r.risk_pct === null || r.risk_pct === undefined ? 1 : Number(r.risk_pct);
    let slDist = 15;
    if (r.entry && r.sl) {
      const d = (Math.abs(r.entry - r.sl) / r.entry) * 100;
      if (d > 0 && isFinite(d)) slDist = d;
    }
    eq += (pnl * risk) / slDist;
    peak = Math.max(peak, eq);
    return { id: r.id, symbol: r.symbol, eq: Math.round(eq * 1000) / 1000, dd: Math.round((eq - peak) * 1000) / 1000, pnl };
  });
}

export type TierStat = { tier: number; n: number; winrate: number; expectancy: number; maxDd: number; flag: string };

export function tierStats(closed: Position[]): TierStat[] {
  return [1, 2].map((tier) => {
    const c = closed.filter((p) => p.tier === tier);
    if (!c.length) return { tier, n: 0, winrate: 0, expectancy: 0, maxDd: 0, flag: "EMPTY" };
    const pnls = c.map((p) => Number(p.pnl_pct ?? 0));
    const wins = pnls.filter((x) => x > 0);
    const losses = pnls.filter((x) => x <= 0);
    const wr = wins.length / pnls.length;
    const aw = wins.length ? wins.reduce((a, b) => a + b, 0) / wins.length : 0;
    const al = losses.length ? Math.abs(losses.reduce((a, b) => a + b, 0) / losses.length) : 0;
    const exp = Math.round((wr * aw - (1 - wr) * al) * 100) / 100;
    let peak = 0, dd = 0, run = 0;
    for (const p of pnls) {
      run += p;
      peak = Math.max(peak, run);
      dd = Math.min(dd, run - peak);
    }
    const flag = c.length >= 20 && exp > 0 ? "OK" : c.length < 20 ? "EXPLORATORY" : "NEGATIVE";
    return { tier, n: c.length, winrate: Math.round(wr * 1000) / 10, expectancy: exp, maxDd: Math.round(dd * 100) / 100, flag };
  });
}

export function vetoTop(signals: Signal[], limit = 8): { name: string; n: number }[] {
  const c = new Map<string, number>();
  for (const s of signals) {
    if (s.verdict !== "REJECT") continue;
    const first = (s.reason || "").split("|")[0].trim();
    if (first.includes("VETO:")) {
      for (const v of first.replace("VETO:", "").split(";")) {
        const k = v.trim().split(":")[0];
        if (k) c.set(k, (c.get(k) ?? 0) + 1);
      }
    } else {
      c.set("CONF_BELOW_THRESHOLD", (c.get("CONF_BELOW_THRESHOLD") ?? 0) + 1);
    }
  }
  return [...c.entries()].map(([name, n]) => ({ name, n })).sort((a, b) => b.n - a.n).slice(0, limit);
}
