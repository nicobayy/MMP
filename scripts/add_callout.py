"""Catat KOL callout manual — dengan standar input (SOP kualitas KOL).
Wajib: --token (contract address, BUKAN cuma ticker).
Usage:
  python scripts/add_callout.py --token MINT --symbol XYZ --handle @kanal --trust trusted --reason whale_buy --source telegram
  python scripts/add_callout.py --list --token MINT
Trust: trusted (terkurasi) / trial (observasi) / untrusted (default, plafon 0.5).
Reason: launch / listing / whale_buy / rotation / narrative / other.
Catatan PowerShell: kutip handle, mis. --handle '@kanal'.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from mmp.config import db_path
from mmp.storage import kol as koldb
from mmp.storage.store import connect


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default=None, help="contract address (wajib)")
    ap.add_argument("--symbol", default="")
    ap.add_argument("--chain", default="solana")
    ap.add_argument("--source", default="telegram", help="telegram / x")
    ap.add_argument("--handle", default="")
    ap.add_argument("--trust", default="", choices=["", "trusted", "trial", "untrusted"])
    ap.add_argument("--trusted", action="store_true", help="shortcut --trust trusted")
    ap.add_argument("--reason", default="", choices=["", *koldb.REASONS])
    ap.add_argument("--note", default="")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    con = connect(db_path())
    koldb.init(con)
    if args.list:
        rows = koldb.recent_for_token(con, args.token or "", hours=24 * 30)
        if not rows:
            print("Belum ada callout untuk token itu.")
        for r in rows:
            # L4: recent_for_token return dict — akses via .get agar tahan refactor.
            _h = r.get("handle", "")
            st = koldb.handle_stats(con, _h) if _h else {}
            w, wlabel = koldb.handle_weight(con, _h, r.get("trust", "trusted"))
            prec = f" prec={st.get('win_rate', 0):.0%} vol={st.get('calls', 0)}calls" if st.get("calls") else " (tanpa outcome)"
            print(f"[{r.get('trust', '?')}/{r.get('reason') or '-'} w={w} {wlabel}] {r['handle']} via {r['source']} @ {r['ts']}{prec}")
        return
    if not args.token:
        ap.print_help()
        return
    from mmp import validators as _v
    if not _v.is_token_address(args.chain, args.token):
        print(f"Token harus contract address ({_v.explain(args.chain, args.token)}), bukan ticker.")
        return
    trust = "trusted" if args.trusted else args.trust
    rid = koldb.add_callout(con, args.token, args.symbol, args.chain, args.source,
                            args.handle, args.trusted, args.note, trust=trust, reason=args.reason)
    print(f"OK callout #{rid} tersimpan (trust={trust or 'untrusted'}, reason={args.reason or '-'}). Aktif 48 jam.")


if __name__ == "__main__":
    main()
