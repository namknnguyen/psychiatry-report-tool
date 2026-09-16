"""Pure-stdlib cryptography for PHI at rest.

The application must run with zero third-party dependencies, so AES-256-GCM is
implemented here directly.  Correctness is pinned by the NIST/FIPS-197 and
NIST GCM test vectors exercised in tests/test_all.py -- do not "optimise" this
module without re-running them.

Design notes for the security review:
  * Record-level authenticated encryption (AES-256-GCM), fresh 96-bit random
    nonce per write, 128-bit tag.
  * Associated data binds every ciphertext to its table + row id, so a
    ciphertext cannot be moved between patients or between columns.
  * The data key is wrapped by a key-encryption-key derived from the operator
    passphrase with PBKDF2-HMAC-SHA256 (600k iterations, per OWASP 2023).
  * Passwords use PBKDF2-HMAC-SHA256 with per-user salt; verification is
    constant time.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from typing import Tuple

# --------------------------------------------------------------------------
# AES-256 block cipher (encryption direction only -- GCM never needs decrypt)
# --------------------------------------------------------------------------

_SBOX = bytes.fromhex(
    "637c777bf26b6fc53001672bfed7ab76"
    "ca82c97dfa5947f0add4a2af9ca472c0"
    "b7fd9326363ff7cc34a5e5f171d83115"
    "04c723c31896059a071280e2eb27b275"
    "09832c1a1b6e5aa0523bd6b329e32f84"
    "53d100ed20fcb15b6acbbe394a4c58cf"
    "d0efaafb434d338545f9027f503c9fa8"
    "51a3408f929d38f5bcb6da2110fff3d2"
    "cd0c13ec5f974417c4a77e3d645d1973"
    "60814fdc222a908846eeb814de5e0bdb"
    "e0323a0a4906245cc2d3ac629195e479"
    "e7c8376d8dd54ea96c56f4ea657aae08"
    "ba78252e1ca6b4c6e8dd741f4bbd8b8a"
    "703eb5664803f60e613557b986c11d9e"
    "e1f8981169d98e949b1e87e9ce5528df"
    "8ca1890dbfe6426841992d0fb054bb16"
)

_RCON = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36)


def _xtime(a: int) -> int:
    a <<= 1
    if a & 0x100:
        a = (a ^ 0x1B) & 0xFF
    return a


# Multiply-by-2 and multiply-by-3 lookup tables for MixColumns.
_M2 = bytes(_xtime(i) for i in range(256))
_M3 = bytes(_xtime(i) ^ i for i in range(256))


def _expand_key(key: bytes) -> list:
    """FIPS-197 key expansion for a 256-bit key -> 15 round keys of 16 bytes."""
    if len(key) != 32:
        raise ValueError("AES-256 requires a 32-byte key")
    nk, nr = 8, 14
    words = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        temp = list(words[i - 1])
        if i % nk == 0:
            temp = temp[1:] + temp[:1]
            temp = [_SBOX[b] for b in temp]
            temp[0] ^= _RCON[i // nk - 1]
        elif i % nk == 4:
            temp = [_SBOX[b] for b in temp]
        words.append([words[i - nk][j] ^ temp[j] for j in range(4)])
    return [bytes(b for w in words[4 * r:4 * r + 4] for b in w) for r in range(nr + 1)]


def _encrypt_block(round_keys: list, block: bytes) -> bytes:
    s = [block[i] ^ round_keys[0][i] for i in range(16)]
    for rnd in range(1, 14):
        # SubBytes + ShiftRows fused: column c of the state after ShiftRows
        # takes bytes 4c, 4c+5, 4c+10, 4c+15 (mod 16) of the previous state.
        t = [
            _SBOX[s[0]], _SBOX[s[5]], _SBOX[s[10]], _SBOX[s[15]],
            _SBOX[s[4]], _SBOX[s[9]], _SBOX[s[14]], _SBOX[s[3]],
            _SBOX[s[8]], _SBOX[s[13]], _SBOX[s[2]], _SBOX[s[7]],
            _SBOX[s[12]], _SBOX[s[1]], _SBOX[s[6]], _SBOX[s[11]],
        ]
        rk = round_keys[rnd]
        s = []
        for c in range(0, 16, 4):
            a0, a1, a2, a3 = t[c], t[c + 1], t[c + 2], t[c + 3]
            s.append(_M2[a0] ^ _M3[a1] ^ a2 ^ a3 ^ rk[c])
            s.append(a0 ^ _M2[a1] ^ _M3[a2] ^ a3 ^ rk[c + 1])
            s.append(a0 ^ a1 ^ _M2[a2] ^ _M3[a3] ^ rk[c + 2])
            s.append(_M3[a0] ^ a1 ^ a2 ^ _M2[a3] ^ rk[c + 3])
    # Final round: SubBytes + ShiftRows + AddRoundKey (no MixColumns).
    t = [
        _SBOX[s[0]], _SBOX[s[5]], _SBOX[s[10]], _SBOX[s[15]],
        _SBOX[s[4]], _SBOX[s[9]], _SBOX[s[14]], _SBOX[s[3]],
        _SBOX[s[8]], _SBOX[s[13]], _SBOX[s[2]], _SBOX[s[7]],
        _SBOX[s[12]], _SBOX[s[1]], _SBOX[s[6]], _SBOX[s[11]],
    ]
    rk = round_keys[14]
    return bytes(t[i] ^ rk[i] for i in range(16))


# --------------------------------------------------------------------------
# GCM mode
# --------------------------------------------------------------------------

_R = 0xE1 << 120


class _GHash:
    """GF(2^128) hash keyed by H.  H is fixed per key, so the 128 shifted
    values of H are precomputed once and multiplication becomes a XOR fold."""

    __slots__ = ("_v",)

    def __init__(self, h: int):
        v = []
        cur = h
        for _ in range(128):
            v.append(cur)
            cur = (cur >> 1) ^ _R if cur & 1 else cur >> 1
        self._v = v

    def mul(self, x: int) -> int:
        z = 0
        v = self._v
        i = 0
        while x:
            if x >> 127:
                z ^= v[i]
            x = (x << 1) & ((1 << 128) - 1)
            i += 1
        return z

    def digest(self, data: bytes) -> int:
        y = 0
        for off in range(0, len(data), 16):
            chunk = data[off:off + 16]
            if len(chunk) < 16:
                chunk = chunk + b"\x00" * (16 - len(chunk))
            y = self.mul(y ^ int.from_bytes(chunk, "big"))
        return y


def _gctr(round_keys: list, icb: bytes, data: bytes) -> bytes:
    if not data:
        return b""
    out = bytearray()
    counter = int.from_bytes(icb[12:], "big")
    prefix = icb[:12]
    for off in range(0, len(data), 16):
        block = data[off:off + 16]
        ks = _encrypt_block(round_keys, prefix + counter.to_bytes(4, "big"))
        out += bytes(a ^ b for a, b in zip(block, ks))
        counter = (counter + 1) & 0xFFFFFFFF
    return bytes(out)


def _gcm_core(key: bytes, nonce: bytes, plaintext: bytes, aad: bytes):
    if len(nonce) != 12:
        raise ValueError("nonce must be 96 bits")
    rk = _expand_key(key)
    h = int.from_bytes(_encrypt_block(rk, b"\x00" * 16), "big")
    gh = _GHash(h)
    j0 = nonce + b"\x00\x00\x00\x01"
    ciphertext = _gctr(rk, nonce + b"\x00\x00\x00\x02", plaintext)

    pad_a = b"\x00" * ((16 - len(aad) % 16) % 16)
    pad_c = b"\x00" * ((16 - len(ciphertext) % 16) % 16)
    lengths = (len(aad) * 8).to_bytes(8, "big") + (len(ciphertext) * 8).to_bytes(8, "big")
    s = gh.digest(aad + pad_a + ciphertext + pad_c + lengths)
    tag = _gctr(rk, j0, s.to_bytes(16, "big"))
    return ciphertext, tag


def aes_gcm_encrypt(key: bytes, nonce: bytes, plaintext: bytes, aad: bytes = b"") -> Tuple[bytes, bytes]:
    return _gcm_core(key, nonce, plaintext, aad)


def aes_gcm_decrypt(key: bytes, nonce: bytes, ciphertext: bytes, tag: bytes, aad: bytes = b"") -> bytes:
    rk = _expand_key(key)
    h = int.from_bytes(_encrypt_block(rk, b"\x00" * 16), "big")
    gh = _GHash(h)
    pad_a = b"\x00" * ((16 - len(aad) % 16) % 16)
    pad_c = b"\x00" * ((16 - len(ciphertext) % 16) % 16)
    lengths = (len(aad) * 8).to_bytes(8, "big") + (len(ciphertext) * 8).to_bytes(8, "big")
    s = gh.digest(aad + pad_a + ciphertext + pad_c + lengths)
    expected = _gctr(rk, nonce + b"\x00\x00\x00\x01", s.to_bytes(16, "big"))
    if not hmac.compare_digest(expected, tag):
        raise ValueError("PHI record failed integrity check (bad tag)")
    return _gctr(rk, nonce + b"\x00\x00\x00\x02", ciphertext)


# --------------------------------------------------------------------------
# Envelope format used by the database layer
# --------------------------------------------------------------------------

ENVELOPE_VERSION = b"\x01"


def seal(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    """version || nonce(12) || tag(16) || ciphertext"""
    nonce = secrets.token_bytes(12)
    ct, tag = aes_gcm_encrypt(key, nonce, plaintext, aad)
    return ENVELOPE_VERSION + nonce + tag + ct


def unseal(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    if not blob or blob[:1] != ENVELOPE_VERSION:
        raise ValueError("unrecognised PHI envelope")
    nonce, tag, ct = blob[1:13], blob[13:29], blob[29:]
    return aes_gcm_decrypt(key, nonce, ct, tag, aad)


# --------------------------------------------------------------------------
# Key derivation / password hashing
# --------------------------------------------------------------------------

KDF_ITERATIONS = 600_000
_PW_ITERATIONS = 240_000


def derive_kek(passphrase: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, KDF_ITERATIONS, 32)


def new_data_key() -> bytes:
    return secrets.token_bytes(32)


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PW_ITERATIONS, 32)
    return f"pbkdf2_sha256${_PW_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, dk_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters), 32)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_fingerprint(token: str) -> str:
    """Session tokens are stored only as a hash, so a database copy does not
    hand an attacker live sessions."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def audit_chain(prev_hash: str, payload: str) -> str:
    """Tamper-evident audit log: each entry hashes the previous entry."""
    return hashlib.sha256((prev_hash + "|" + payload).encode("utf-8")).hexdigest()


def random_hex(n: int = 8) -> str:
    return os.urandom(n).hex()
