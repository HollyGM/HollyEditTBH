"""
Save layer: decrypts/encrypts .es3 SaveFile (Easy Save 3, AES-128-CBC),
unpacks the nested JSON structure within it (Account/Player), and recalculates
SystemInfo (integrity HMAC) during saving. No mandatory dependencies (uses 'cryptography'
if available, otherwise falls back to the built-in pure AES implementation).
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import shutil
import tempfile
import time
from hashlib import pbkdf2_hmac
 
# --- keys/constants (Taskbar Hero 1.00.17) ---
ES3_PASSWORD = "emuMqG3bLYJ938ZDCfieWJ"  # encryption password for Easy Save 3
PBKDF2_ITERS = 100
KEY_SIZE = 16
IV_SIZE = 16
# HMAC-SHA256 key for integrity ("SystemInfo" field); retrieved at runtime and validated.
SYSTEMINFO_HMAC_KEY = bytes.fromhex("93d9429e9b72f22fdb3413193763eaba1e8cfae995f61466a81a36a609d8e456")
SYSTEMINFO_SEP = "|"


def _system_info_value(account_json, player_json, owner_steam_id):
    message = SYSTEMINFO_SEP.join([account_json, player_json, str(owner_steam_id)]).encode("utf-8")
    digest = hmac.new(SYSTEMINFO_HMAC_KEY, message, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")
 
# --- AES-CBC: use 'cryptography' (faster) if available, otherwise use inline pure AES ---
try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
 
    def _aes_cbc_decrypt(key, iv, data):
        d = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        return d.update(data) + d.finalize()
 
    def _aes_cbc_encrypt(key, iv, data):
        e = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
        return e.update(data) + e.finalize()
 
    AES_BACKEND = "cryptography"
except Exception:
    # 'cryptography' is not installed -> fall back to the pure AES-128 Python implementation
    # at the bottom of this file (without any external dependencies).
    def _aes_cbc_decrypt(key, iv, data):
        return _pure_cbc_decrypt(key, iv, data)
 
    def _aes_cbc_encrypt(key, iv, data):
        return _pure_cbc_encrypt(key, iv, data)
 
    AES_BACKEND = "pure-python"
 
 
def _pkcs7_pad(data, block=16):
    n = block - (len(data) % block)
    return data + bytes([n]) * n
 
 
def _pkcs7_unpad(data):
    if not data:
        raise ValueError("empty encrypted payload")
    n = data[-1]
    if n < 1 or n > 16:
        raise ValueError("invalid PKCS7 padding")
    if data[-n:] != bytes([n]) * n:
        raise ValueError("invalid PKCS7 padding bytes")
    return data[:-n]
 
 
def _derive_key(password, iv):
    return pbkdf2_hmac("sha1", password.encode("utf-8"), iv, PBKDF2_ITERS, dklen=KEY_SIZE)
 
 
def es3_decrypt(raw, password=ES3_PASSWORD):
    if len(raw) < IV_SIZE * 2 or (len(raw) - IV_SIZE) % IV_SIZE:
        raise ValueError("invalid ES3 encrypted payload length")
    iv, ct = raw[:IV_SIZE], raw[IV_SIZE:]
    key = _derive_key(password, iv)
    return _pkcs7_unpad(_aes_cbc_decrypt(key, iv, ct))
 
 
def es3_encrypt(plaintext, password=ES3_PASSWORD, iv=None):
    if iv is None:
        iv = secrets.token_bytes(IV_SIZE)
    key = _derive_key(password, iv)
    return iv + _aes_cbc_encrypt(key, iv, _pkcs7_pad(plaintext))
 
 
class SaveFile:
    """Loaded and unpacked save file. `account` and `player` are editable dicts."""
 
    def __init__(self, es3_obj, password=ES3_PASSWORD):
        if not isinstance(es3_obj, dict):
            raise ValueError("invalid ES3 root: expected an object")
        for field in ("AccountSaveData", "PlayerSaveData", "SystemInfo"):
            record = es3_obj.get(field)
            if not isinstance(record, dict) or not isinstance(record.get("value"), str):
                raise ValueError(f"invalid ES3 structure: missing {field}.value")
        self._es3 = es3_obj  # external ES3 structure {key: {__type, value}}
        self.password = password
        account_json = es3_obj["AccountSaveData"]["value"]
        player_json = es3_obj["PlayerSaveData"]["value"]
        self.account = json.loads(account_json)
        self.player = json.loads(player_json)
        if not isinstance(self.account, dict) or not isinstance(self.player, dict):
            raise ValueError("invalid ES3 save: AccountSaveData and PlayerSaveData must contain objects")
        expected = _system_info_value(account_json, player_json, self.account.get("ownerSteamId", ""))
        self.integrity_valid = hmac.compare_digest(es3_obj["SystemInfo"]["value"], expected)
        self.last_backup_path = None
 
    @classmethod
    def load(cls, path, password=ES3_PASSWORD):
        with open(path, "rb") as fh:
            raw = fh.read()
        es3_obj = json.loads(es3_decrypt(raw, password).decode("utf-8"))
        return cls(es3_obj, password)
 
    def _serialize_inner(self, obj):
        # compact, raw UTF-8; semantically equivalent to Newtonsoft
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
 
    def to_es3_bytes(self):
        acc = self._serialize_inner(self.account)
        ply = self._serialize_inner(self.player)
        steam = str(self.account.get("ownerSteamId", ""))
        sysinfo = _system_info_value(acc, ply, steam)
 
        self._es3["AccountSaveData"]["value"] = acc
        self._es3["PlayerSaveData"]["value"] = ply
        self._es3["SystemInfo"]["value"] = sysinfo
        self.integrity_valid = True
 
        text = json.dumps(self._es3, ensure_ascii=False, indent="\t")
        return es3_encrypt(text.encode("utf-8"), self.password)
 
    def save(self, path, backup=True):
        blob = self.to_es3_bytes()
        path = os.path.abspath(os.fspath(path))
        parent = os.path.dirname(path) or "."
        self.last_backup_path = None
        if backup and os.path.exists(path):
            stem, ext = os.path.splitext(path)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            backup_path = f"{stem}_backup_{stamp}{ext}"
            suffix = 2
            while os.path.exists(backup_path):
                backup_path = f"{stem}_backup_{stamp}_{suffix}{ext}"
                suffix += 1
            shutil.copy2(path, backup_path)
            self.last_backup_path = backup_path

        fd, temp_path = tempfile.mkstemp(prefix=".tbh-save-", suffix=".tmp", dir=parent)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(blob)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(temp_path, path)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
        return path
 
 
# ============================================================================
# Pure Python AES-128 (fallback) - only used if the 'cryptography' library
# is not installed. Follows the official FIPS-197 specification (S-box, key
# schedule/expansion, SubBytes, ShiftRows, MixColumns). Not as fast as
# a C-based implementation, but sufficient for small save files and
# requires no external dependencies.
# ============================================================================
 
# Standard AES S-box (256 bytes)
_AES_SBOX = (
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16,
)
 
# Inverse S-box, computed once from the S-box above (used during decryption)
_AES_INV_SBOX = [0] * 256
for _i, _v in enumerate(_AES_SBOX):
    _AES_INV_SBOX[_v] = _i
_AES_INV_SBOX = tuple(_AES_INV_SBOX)
del _i, _v
 
# Round constants (Rcon) for AES-128 key expansion (10 rounds)
_RCON = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36, 0x6C, 0xD8, 0xAB, 0x4D)
 
 
def _gmul(a, b):
    """Multiplication in Galois Field GF(2^8), used by MixColumns/InvMixColumns."""
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p
 
 
def _key_expansion(key):
    """Transforms a 16-byte key into 11 round keys (16 bytes each) for AES-128."""
    Nk = 4   # number of words (32-bit) in the key
    Nr = 10  # number of rounds for AES-128
    w =[list(key[4 * i:4 * i + 4]) for i in range(Nk)]
    for i in range(Nk, 4 * (Nr + 1)):
        temp = list(w[i - 1])
        if i % Nk == 0:
            temp = temp[1:] + temp[:1]                 # RotWord
            temp = [_AES_SBOX[b] for b in temp]         # SubWord
            temp[0] ^= _RCON[i // Nk - 1]               # XOR with Rcon
        w.append([w[i - Nk][j] ^ temp[j] for j in range(4)])
    round_keys = []
    for r in range(Nr + 1):
        rk = []
        for c in range(4):
            rk.extend(w[r * 4 + c])
        round_keys.append(bytes(rk))
    return round_keys
 
 
def _add_round_key(state, rk):
    return bytes(s ^ k for s, k in zip(state, rk))
 
 
def _sub_bytes(state):
    return bytes(_AES_SBOX[b] for b in state)
 
 
def _inv_sub_bytes(state):
    return bytes(_AES_INV_SBOX[b] for b in state)
 
 
def _shift_rows(state):
    # state is arranged column-major: bytes 0-3 = column 0, bytes 4-7 = column 1, etc.
    s = state
    return bytes([
        s[0], s[5], s[10], s[15],
        s[4], s[9], s[14], s[3],
        s[8], s[13], s[2], s[7],
        s[12], s[1], s[6], s[11],
    ])
 
 
def _inv_shift_rows(state):
    s = state
    return bytes([
        s[0], s[13], s[10], s[7],
        s[4], s[1], s[14], s[11],
        s[8], s[5], s[2], s[15],
        s[12], s[9], s[6], s[3],
    ])
 
 
def _mix_single_column(c):
    a0, a1, a2, a3 = c
    r0 = _gmul(a0, 2) ^ _gmul(a1, 3) ^ a2 ^ a3
    r1 = a0 ^ _gmul(a1, 2) ^ _gmul(a2, 3) ^ a3
    r2 = a0 ^ a1 ^ _gmul(a2, 2) ^ _gmul(a3, 3)
    r3 = _gmul(a0, 3) ^ a1 ^ a2 ^ _gmul(a3, 2)
    return [r0, r1, r2, r3]
 
 
def _inv_mix_single_column(c):
    a0, a1, a2, a3 = c
    r0 = _gmul(a0, 0x0e) ^ _gmul(a1, 0x0b) ^ _gmul(a2, 0x0d) ^ _gmul(a3, 0x09)
    r1 = _gmul(a0, 0x09) ^ _gmul(a1, 0x0e) ^ _gmul(a2, 0x0b) ^ _gmul(a3, 0x0d)
    r2 = _gmul(a0, 0x0d) ^ _gmul(a1, 0x09) ^ _gmul(a2, 0x0e) ^ _gmul(a3, 0x0b)
    r3 = _gmul(a0, 0x0b) ^ _gmul(a1, 0x0d) ^ _gmul(a2, 0x09) ^ _gmul(a3, 0x0e)
    return [r0, r1, r2, r3]
 
 
def _mix_columns(state):
    out = []
    for c in range(4):
        out.extend(_mix_single_column(state[4 * c:4 * c + 4]))
    return bytes(out)
 
 
def _inv_mix_columns(state):
    out = []
    for c in range(4):
        out.extend(_inv_mix_single_column(state[4 * c:4 * c + 4]))
    return bytes(out)
 
 
def _aes_encrypt_block(block, round_keys):
    """Encrypts a single 16-byte block (internal ECB mode) with AES-128."""
    Nr = 10
    state = _add_round_key(block, round_keys[0])
    for rnd in range(1, Nr):
        state = _sub_bytes(state)
        state = _shift_rows(state)
        state = _mix_columns(state)
        state = _add_round_key(state, round_keys[rnd])
    state = _sub_bytes(state)
    state = _shift_rows(state)
    state = _add_round_key(state, round_keys[Nr])  # final round without MixColumns
    return state
 
 
def _aes_decrypt_block(block, round_keys):
    """Decrypts a single 16-byte block (internal ECB mode) with AES-128."""
    Nr = 10
    state = _add_round_key(block, round_keys[Nr])
    for rnd in range(Nr - 1, 0, -1):
        state = _inv_shift_rows(state)
        state = _inv_sub_bytes(state)
        state = _add_round_key(state, round_keys[rnd])
        state = _inv_mix_columns(state)
    state = _inv_shift_rows(state)
    state = _inv_sub_bytes(state)
    state = _add_round_key(state, round_keys[0])
    return state
 
 
def _pure_cbc_encrypt(key, iv, data):
    """CBC mode encryption. `data` must already be a multiple of 16 bytes
    (PKCS7 padding is performed by `_pkcs7_pad` before this function is called)."""
    round_keys = _key_expansion(key)
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        block = bytes(b ^ p for b, p in zip(data[i:i + 16], prev))
        enc = _aes_encrypt_block(block, round_keys)
        out.extend(enc)
        prev = enc
    return bytes(out)
 
 
def _pure_cbc_decrypt(key, iv, data):
    """CBC mode decryption. Returns the plaintext still containing PKCS7 padding
    (unpadding is performed by `_pkcs7_unpad` outside of this function)."""
    round_keys = _key_expansion(key)
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        block = data[i:i + 16]
        dec = _aes_decrypt_block(block, round_keys)
        out.extend(b ^ p for b, p in zip(dec, prev))
        prev = block
    return bytes(out)
