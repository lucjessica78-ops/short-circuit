"""
Offline license key system for PandaSC.

How it works
------------
A license key encodes an 8-byte payload (a random license id + an optional
expiry date, in days-since-epoch) plus a 6-byte HMAC-SHA256 signature over
that payload, all Base32-encoded into a readable XXXX-XXXX-... string.

Validating a key only requires the SECRET below -- no server, no internet
connection. That is what makes the app fully standalone. The trade-off (be
upfront with customers/yourself about this) is that anyone who extracts
SECRET from the compiled binary could mint their own keys. This is the
standard level of protection for a small offline desktop tool; it stops
casual copying and key-sharing, not a determined reverse engineer. If you
ever want harder protection, move validation to a small web endpoint you
control and check the key online instead.

IMPORTANT: change SECRET below to your own random value before you sell
this, and keep seller_tools/keygen.py private -- never ship it with the app.
"""
import base64
import hashlib
import hmac
import os
import struct
import time
import uuid

# --- CHANGE THIS before shipping. Keep it secret, keep it out of git. ---
SECRET = b"REPLACE-THIS-WITH-YOUR-OWN-64-CHAR-RANDOM-SECRET-BEFORE-YOU-SHIP-1234"

PRODUCT_CODE = "PANDASC1"


def _sig(payload: bytes) -> bytes:
    return hmac.new(SECRET, payload, hashlib.sha256).digest()[:6]


def generate_key(days_valid: int | None = None) -> str:
    """Create a new license key. days_valid=None means it never expires."""
    rand_id = os.urandom(4)
    if days_valid is None:
        expiry_days = 0  # 0 = no expiry
    else:
        expiry_days = int(time.time() // 86400) + int(days_valid)
        if expiry_days <= 0:
            expiry_days = 1
    payload = rand_id + struct.pack(">I", expiry_days)
    sig = _sig(payload)
    raw = payload + sig
    b32 = base64.b32encode(raw).decode().rstrip("=")
    groups = [b32[i:i + 4] for i in range(0, len(b32), 4)]
    return "-".join(groups)


def _decode(key: str) -> bytes | None:
    try:
        b32 = key.strip().upper().replace("-", "").replace(" ", "")
        pad = "=" * (-len(b32) % 8)
        return base64.b32decode(b32 + pad)
    except Exception:
        return None


def validate_key(key: str) -> tuple[bool, str]:
    """Returns (is_valid, message)."""
    raw = _decode(key)
    if raw is None or len(raw) != 14:
        return False, "That key doesn't look right. Check for typos."
    payload, sig = raw[:8], raw[8:]
    if not hmac.compare_digest(sig, _sig(payload)):
        return False, "This key isn't recognized."
    expiry_days = struct.unpack(">I", payload[4:8])[0]
    if expiry_days != 0:
        today = int(time.time() // 86400)
        if today > expiry_days:
            return False, "This key has expired."
    return True, "OK"


def machine_id() -> str:
    """A rough per-machine fingerprint, used only to flag key-sharing."""
    return hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()[:16]


def _config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    path = os.path.join(base, "PandaSC")
    os.makedirs(path, exist_ok=True)
    return path


def _license_file() -> str:
    return os.path.join(_config_dir(), "license.json")


def load_activation():
    import json
    path = _license_file()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            data = json.load(f)
        ok, _ = validate_key(data.get("key", ""))
        if not ok:
            return None
        return data
    except Exception:
        return None


def save_activation(key: str):
    import json
    data = {"key": key, "machine_id": machine_id(), "activated_at": int(time.time())}
    with open(_license_file(), "w") as f:
        json.dump(data, f)
    return data


def current_status():
    data = load_activation()
    if not data:
        return {"activated": False}
    ok, msg = validate_key(data["key"])
    same_machine = data.get("machine_id") == machine_id()
    return {
        "activated": ok,
        "same_machine": same_machine,
        "message": msg,
    }
