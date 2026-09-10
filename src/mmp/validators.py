"""Validasi format address input pengguna (bukan verifikasi on-chain).
Tujuan: gagal cepat dengan pesan jelas SEBELUM bakar API call, bukan
bukti token aman. Validasi keamanan sesungguhnya tetap di risk.py.
M5: bedakan validator token vs pair secara semantik walau formatnya
sama (base58 Solana / 0x-hex EVM) agar pesan error jujur.
"""
from __future__ import annotations

_B58 = frozenset("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
_HEX = frozenset("0123456789abcdefABCDEF")


def is_solana_address(addr: str) -> bool:
    a = (addr or "").strip()
    return 32 <= len(a) <= 44 and all(c in _B58 for c in a)


def is_evm_address(addr: str) -> bool:
    a = (addr or "").strip()
    return len(a) == 42 and a.startswith("0x") and all(c in _HEX for c in a[2:])


def is_token_address(chain: str, addr: str) -> bool:
    if (chain or "") == "solana":
        return is_solana_address(addr)
    return is_evm_address(addr)


def is_pair_address(chain: str, addr: str) -> bool:
    """M5: format pair-address DexScreener sama dengan token-address
    (base58 Solana / 0x-hex EVM), tapi dipisah agar pesan salah input
    menyebut 'pair', bukan 'token'."""
    return is_token_address(chain, addr)


def explain(chain: str, addr: str) -> str:
    if (chain or "") == "solana":
        return "alamat Solana = base58 32-44 karakter"
    return "alamat EVM = 0x + 40 hex"


def explain_pair(chain: str, addr: str) -> str:
    if (chain or "") == "solana":
        return "alamat pair Solana = base58 32-44 karakter"
    return "alamat pair EVM = 0x + 40 hex"
