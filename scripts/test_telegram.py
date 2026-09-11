"""Test kredensial Telegram tanpa scan: python scripts/test_telegram.py"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
from mmp.notifiers.telegram import creds, send_telegram  # noqa: E402


def main():
    token, chat = creds()
    if not token or not chat:
        print("BELUM DIISI. Cara setup:")
        print("1. Chat ke @BotFather -> /newbot -> dapat token")
        print("2. Chat ke bot kamu, kirim /start")
        print("3. Buka https://api.telegram.org/bot<TOKEN>/getUpdates -> salin chat id")
        print("4. copy .env.example .env lalu isi TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID")
        return
    ok = send_telegram("🟢 <b>MMP test</b>: bot terhubung. Alert PASS akan masuk ke chat ini.")
    print("Terkirim. Cek Telegram." if ok else "GAGAL. Cek token/chat id & koneksi.")

if __name__ == "__main__":
    main()
