# MMP — Melok Melok Profit
Sistem intelijen trading yang sangat konservatif & berorientasi precision tinggi.

## Prinsip Inti
1. **Precision > Recall.** Lebih baik TIDAK kasih sinyal daripada kasih sinyal lemah. Target: sedikit sinyal, tapi confidence sangat tinggi.
2. **Konservatif by design.** Ada HARD VETO: satu red flag fatal = sinyal dibatalkan, berapapun skornya.
3. **Expectancy positif.** Setiap sinyal wajib punya TP/SL + position size + alasan exit capability jelas.
4. **Multi-chain.** Arsitektur collector pluggable: Solana dulu (MVP), EVM (ETH/BSC/Base) tinggal tambah collector.

## Funnel MMP (kenapa risiko kecil)
```
Universe (DexScreener boosts/search)
  → Liquidity & Exit Filter (bisa keluar apa tidak?)
  → Risk Filter / HARD VETO (honeypot, mint, tax, LP lock, holder集中)
  → Token Metrics (momentum, volume, FDV/MC, umur, holder)
  → Smart Money confluence (tracker wallet)
  → KOL / Callout confluence
  → Scoring (0-100) + Gate (>=85 baru PASS)
  → Risk sizing (TP/SL, max risk 1-2%)
  → Sinyal Telegram + Log SQLite
```

Skor default TIDAK akan lolos kalau data Smart Money / KOL kosong — ini disengaja agar konservatif.
Untuk testing, ada mode `--permissive` yang menurunkan threshold.

## Struktur
```
config/mmp_config.yaml   <- semua threshold, bisa di-tune tanpa ubah kode
src/mmp/
  collectors/dexscreener.py  <- universe utama multi-chain (gratis)
  collectors/geckoterminal.py<- universe fallback EVM (gratis)
  collectors/helius.py       <- holder + mint authority Solana (butuh key)
  collectors/birdeye.py      <- cross-check holder/vol Solana (butuh key)
  collectors/universe.py     <- gabung + sort (Solana prioritas)
  analyzers/risk.py          <- hard veto
  analyzers/liquidity.py     <- exit capability
  analyzers/token_metrics.py
  analyzers/smart_money.py   <- list manual (opsional)
  analyzers/smart_money_auto.py <- auto-discovery + bonus wallet terpercaya
  analyzers/kol.py           <- callout DB 48 jam terakhir
  engine/scoring.py          <- weighted confidence
  engine/gate.py             <- PASS / REJECT + alasan
  engine/signal.py
  risk/position.py           <- TP/SL + sizing + expectancy
  backtest/engine.py         <- settle TP/SL + ringkasan expectancy
  notifiers/telegram.py      <- alert PASS + summary (cooldown anti-spam)
  storage/store.py           <- sinyal + sent_alerts
  storage/wallets.py         <- win-rate tracker
  storage/kol.py             <- callout DB
  storage/paper.py           <- posisi paper virtual
scripts/run_scan.py          <- scan utama (--notify --paper --chains)
scripts/scheduler.py         <- loop berkala + auto-settle paper
scripts/paper.py             <- list / settle / report paper
scripts/backtest.py          <- ukur return PASS vs harga live
scripts/add_callout.py       <- catat KOL callout
scripts/build_wallets.py     <- kumpulkan kandidat wallet
scripts/record_outcome.py    <- catat win/loss wallet
scripts/test_telegram.py     <- tes bot
scripts/export_json.py       <- ekspor SQLite -> web/public/data/*.json (kontrak dashboard)
web/                         <- dashboard baru (Vite + React + TS, tanpa Python saat viewing)
tests/
```

## Cara Jalan (Python 3.12 — Windows / Linux / macOS)
```powershell
cd MMP
pip install -r requirements.txt   # repro eksak: pip install -r requirements-lock.txt
copy .env.example .env    # Windows — Linux/macOS: cp .env.example .env
# isi HELIUS_API_KEY, BIRDEYE_API_KEY, TELEGRAM_BOT_TOKEN/CHAT_ID
# Opsional (perintah ringkas): pip install -e . -> mmp-scan, mmp-paper,
# mmp-backtest, mmp-scheduler, mmp-callout, mmp-wallets, mmp-telegram-test, mmp-killswitch
# Scan 1 token Solana via address:
python scripts/run_scan.py --token So11111111111111111111111111111111111111112 --chain solana
# Scan multi-chain + Telegram + paper:
python scripts/run_scan.py --top-boosts --limit 5 --chains solana,base --notify --paper
# Mode testing (lebih longgar):
python scripts/run_scan.py --top-boosts --limit 10 --permissive
# Loop berkala (scheduler):
python scripts/scheduler.py --interval-min 60 --limit 5 --chains solana,base --notify --paper
# LIVE 24/7 satu perintah (scheduler + dashboard web + export otomatis):
python scripts/live.py --chains solana,base --port 8080
# Kill switch (hentikan semua):
python scripts/killswitch.py --on   # --off untuk nyalakan lagi
# KOL callout:
python scripts/add_callout.py --token MINT --symbol XYZ --handle @kanal --trusted
# Paper + backtest:
python scripts/paper.py --settle
python scripts/paper.py --report
python scripts/backtest.py --limit 50
# Replay candle-accurate + kalibrasi bucket:
python scripts/replay.py --limit 10
python scripts/calibrate.py
python scripts/ohlcv_check.py --chain base --pool 0xABC...
# Dashboard web (tanpa Python saat viewing):
python scripts/export_json.py   # SQLite -> web/public/data/*.json (otomatis tiap round scheduler)
cd web && npm install && npm run dev   # develop (http://localhost:5173)
cd web && npm run build                # produksi -> web/dist (serve statis; JSON di-mirror ke dist/data tiap ekspor)
# Jalankan test:
pytest -q
```

## Docker
```bash
docker build -t mmp .
docker run --rm -v $(pwd)/data:/app/data --env-file .env mmp \
  python scripts/run_scan.py --top-boosts --limit 5 --chains solana,base --notify --paper
```
DB & histori di-mount via volume agar tak hilang tiap rebuild.

## VPS 24/7 (satu perintah + systemd)
```bash
# Di VPS (Ubuntu): clone, venv, install
python3.12 -m venv venv && venv/bin/pip install -r requirements.txt
cp .env.example .env   # isi key Telegram/Helius/Birdeye
cd web && npm install && npm run build && cd ..
# Jalan 24/7: scheduler + dashboard :8080 + export otomatis
venv/bin/python scripts/live.py --chains solana,base --port 8080
# Autostart via systemd: sesuaikan User/WorkingDirectory di deploy/mmp.service, lalu:
sudo cp deploy/mmp.service /etc/systemd/system/mmp.service
sudo systemctl enable --now mmp
journalctl -u mmp -f   # lihat log
```
Dashboard bind `0.0.0.0` — batasi via firewall (`ufw allow 8080`) atau reverse-proxy
(nginx/caddy) bila dibuka ke publik. JSON `/data/*.json` selalu no-cache.

## Catatan jujur (bukan klaim)
- LP-lock on-chain tidak ada API publik gratis yang reliabel → MMP memakai proxy
  konservatif: mint authority (Helius) + konsentrasi top holders + penalti skor bila data kosong.
- Backtest V1 = forward-measure (entry DB vs harga live), bukan backtest candle historis.
  Jangan pakai uang asli sebelum paper report expectancy > 0 dari minimal 20 posisi closed.
- PnL paper/backtest = bersih setelah asumsi biaya (`paper.slippage_pct` + `fee_pct` per sisi).
  Asumsi default optimistis untuk memecoin tipis — naikkan bila spread lebar.
- Single-operator tool: SQLite + cache in-memory cukup untuk 1 operator.
  Concurrency via ThreadPool (pool besar, semaphore PER SUMBER di
  `concurrency.per_source`) + koneksi DB per-thread; budget API per-run
  di `api_budgets` (trip -> fail-closed, bukan crash).
- Bukan untuk multi-user / HFT. Eksekusi real (swap/MEV) di luar cakupan by design.
- Replay candle = estimasi optimistis-menengah (candle hourly menyembunyikan
  whipsaw intra-jam; sentuhan TP+SL satu candle dimenangkan SL).

## Log keputusan (ditolak/ditunda + syarat revisit)

- **Scraper KOL otomatis: DITOLAK untuk kini.** Butuh kredensial Telegram /
  API X berbayar + rapuh terhadap ToS/layout + risiko flag akun. Manual via
  `add_callout.py` lebih stabil. Revisit bila volume callout manual sudah
  tinggi. Yang otomatis: win-rate handle dari outcome paper.
- **Eksekusi real: DITOLAK sampai paper >= 20 CLOSED** (syarat minimum untuk
  MULAI evaluasi, bukan lampu hijau). Catatan: 20 sampel sangat kecil untuk
  memecoin; hitung expectancy TERPISAH per tier (T1 vs T2) agar satu tier
  negatif tak tersembunyi rata-rata. MEV/private-RPC jadi prasyarat saat tiba.
- **OHLCV historis: forward-replay dulu.** Repo muda -> belum ada histori PASS
  lama; pola utama = sinyal baru dicatat lalu candle diputar ke depan.
  Kandungan histori gratis dicek via `scripts/ohlcv_check.py --chain --pool`.
- **HIGH-1 (otomatis vs manual): KEPUTUSAN FINAL.**
  - Opsi 2 (longgarkan gembok dual-source) DITOLAK permanen. Butuh lebih banyak
    sinyal = longgarkan ANGKA threshold (bisa dikalibrasi balik pakai data),
    bukan melubangi verifikasi (dual cross-check, fail-closed, freeze veto).
  - Opsi 1 DITERIMA sebagai SOP: **Tier-1 Solana = human-in-the-loop by design**
    (tanpa LP-lock on-chain gratis, 85 tak tertembus tanpa konfirmasi KOL —
    ini konsekuensi desain konservatif, bukan bug). Tier-2, khususnya EVM,
    tetap punya jalur full-otomatis.
  - Opsi 3 BERJALAN PARALEL, termurah dulu: scheduler EVM saja 1-2 minggu
    (gratis, tanpa key) -> kalibrasi Tier-2 -> bila expectancy positif baru
    pertimbangkan beli key Helius+Birdeye untuk Solana. Bootstrap KOL manual
    jalan terus untuk mengisi handle_stats. Geser 75/85 hanya via calibrate.py.

## SOP operasional mingguan
1. Scheduler EVM: `scheduler.py --chains base,bsc,ethereum --notify --paper`.
2. Whale feed (butuh Helius key, jadwal terpisah 1-2 jam):
   `whale_watch.py [--wallets 10] [--sigs 20]` -> bonus SM HANYA dari wallet
   ranked + buy >= `whale_min_sol`. Seed awal: `seed_wallets.py --file seeds.txt`.
   Batas jujur: whale EVM belum ada feed trader (konsentrasi holder + tax saja).
3. Bootstrap KOL (standar input: contract address wajib + trust tier + reason):
   `add_callout.py --token MINT --handle @x --trust trial --reason whale_buy`.
4. Settle + report: `paper.py --settle --report` (wallets ter-feed otomatis).
5. Kalibrasi: `calibrate.py` per-tier; angka 75/85 tak digeser tanpa buktinya.
6. Cakupan: `stats.py` tiap minggu — hp_gap >50% baru justifikasi sumber baru.
7. Bukti + ops: `report.py` (expectancy per-tier, max DD, veto top) dan
   `ops_check.py` harian anti-lupa (feed STALE vs OK).

## Konfigurasi
Lihat `config/mmp_config.yaml`. Kunci:
- `signal.min_confidence: 85` — TIER-1 (size penuh).
- `tiers.tier2_min: 75` — TIER-2 (size ½, paper-wajib) khusus sinyal 75–84
  dengan **dual-source yang setuju**: Solana = Helius+Birdeye (mcap/liq beda
  max `dual_max_divergence: 3x`), EVM = DexScreener+honeypot.is (tax diketahui,
  bukan honeypot). Konflik angka antar-sumber = bukan dual = REJECT.
- `risk.*` — veto fatal (`mintable-risk`, `freezable-risk`, `honeypot` otomatis
  veto; `veto_on_blind: true` = buta data ikut veto, default false).
- **PERINGATAN DEFAULT:** `veto_on_blind` default **false**, artinya token dengan
  data keamanan buta total (grade BLIND, tanpa Helius/Birdeye/honeypot.is)
  tetap masuk scoring biasa — hanya kena penalti skor + cap, bukan veto.
  Ini pilihan sadar (agar sistem bisa jalan tanpa key), BUKAN kelalaian:
  aktifkan `true` bila kamu mau mode paling ketat.
- Setiap sinyal membawa `meta.data_grade` (COMPLETE/PARTIAL/BLIND) + `meta.dual`.
- `portfolio.*` — guard max open/per-chain/daily-stop + kill switch `data/STOP`.
- CI otomatis di `.github/workflows/ci.yml` (compile + pytest + secret hygiene).

## Roadmap
- [x] Collector GeckoTerminal (EVM fallback + cross-check)
- [x] Collector Helius (holder + mint authority Solana real; LP-lock via proxy konservatif)
- [x] Smart money wallet DB + Birdeye cross-check (tanpa key = graceful off)
- [x] KOL tracker (callout DB + window 48 jam, trusted berbobot)
- [x] Backtester (forward-measure) + paper trading (TP/SL settle + report)
- [x] Dashboard web + histori sinyal
- [x] Scheduler berkala + Telegram alert anti-spam

> Filosofi: MMP itu filter, bukan radar. Radar memberi banyak titik. Filter hanya meloloskan yang layak.
