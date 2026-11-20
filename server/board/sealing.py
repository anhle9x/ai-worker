"""Sealing of the OTP secrets in accounts.db with a key kept outside it (/etc/ai-worker-otp.key, root only, handed over by systemd), so a copy of keys/ or of a backup gives no login; root on the running server can still read the key.
Niêm phong khoá OTP trong accounts.db bằng một khoá để ngoài nó (/etc/ai-worker-otp.key, chỉ root, do systemd trao), để bản chép keys/ hay bản sao lưu không cho đăng nhập; root trên máy chủ đang chạy vẫn đọc được khoá."""

# Standard library only: HMAC-SHA256 in counter mode is the keystream, and a second HMAC-SHA256 over the version, the name, the nonce and
# the ciphertext is the tag (encrypt, then MAC), so a sealed secret copied onto another account does not open.
# Chỉ thư viện chuẩn: HMAC-SHA256 ở chế độ bộ đếm là dòng khoá, và một HMAC-SHA256 thứ hai trên phiên bản, tên, nonce và
# bản mã là thẻ (mã hoá rồi mới xác thực), nên khoá đã niêm phong chép sang tài khoản khác thì không mở được.

import base64
import hashlib
import hmac
import os
import re
import secrets
import sys

PREFIX = "sealed1:"
KEY_FILE_DEFAULT = "/etc/ai-worker-otp.key"
# the name systemd's LoadCredential gives the key inside $CREDENTIALS_DIRECTORY
# tên mà LoadCredential của systemd đặt cho khoá bên trong $CREDENTIALS_DIRECTORY
CREDENTIAL_NAME = "otp-key"
NONCE_BYTES = 16
TAG_BYTES = 32


def new_key_text() -> str:
    """A new key as it is written to the key file: 64 hex digits and a new line.
    Một khoá mới đúng như ghi vào file khoá: 64 chữ số hex và một dòng mới."""
    return secrets.token_hex(32) + "\n"


def parse_key(text: str) -> bytes:
    """The key in a key file's text; ValueError when it is not 64 hex digits.
    Khoá trong nội dung một file khoá; ValueError khi không phải 64 chữ số hex."""
    t = text.strip()
    if not re.fullmatch(r"[0-9a-fA-F]{64}", t):
        raise ValueError("the OTP key file must hold 64 hex digits")
    return bytes.fromhex(t)


def load_key():
    """The key from systemd's credential, else from OTP_KEY_FILE (default /etc/ai-worker-otp.key); None when there is none to read.
    Khoá lấy từ credential của systemd, không có thì từ OTP_KEY_FILE (mặc định /etc/ai-worker-otp.key); None khi không đọc được."""
    paths = []
    # set by systemd for a service with LoadCredential, not a setting of ours
    # do systemd đặt cho dịch vụ có LoadCredential, không phải cài đặt của chương trình này
    creds = os.getenv("CREDENTIALS_DIRECTORY") or ""
    if creds:
        paths.append(os.path.join(creds, CREDENTIAL_NAME))
    paths.append(os.environ.get("OTP_KEY_FILE", "") or KEY_FILE_DEFAULT)
    for path in paths:
        try:
            with open(path, encoding="ascii") as f:
                return parse_key(f.read())
        except FileNotFoundError:
            continue
        except PermissionError:
            # the default file belongs to root: the webhook gets it through systemd, a command run as the webhook's user does not
            # file mặc định thuộc root: webhook nhận nó qua systemd, lệnh chạy bằng tài khoản của webhook thì không
            continue
        except (OSError, ValueError) as e:
            sys.stderr.write("cannot read the OTP key %s: %s\n" % (path, e))
    return None


def _sub(key: bytes, label: bytes) -> bytes:
    return hmac.new(key, b"ai-worker otp " + label, hashlib.sha256).digest()


def key_id(key: bytes) -> str:
    """A short fingerprint of the key, kept in the database to tell a wrong key from the right one; it reveals nothing of the key.
    Dấu vân tay ngắn của khoá, giữ trong cơ sở dữ liệu để phân biệt khoá sai với khoá đúng; nó không để lộ gì về khoá."""
    return _sub(key, b"id").hex()[:16]


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    enc = _sub(key, b"enc v1")
    out = b""
    counter = 0
    while len(out) < length:
        out += hmac.new(enc, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        counter += 1
    return out[:length]


def _tag(key: bytes, name: str, nonce: bytes, ct: bytes) -> bytes:
    mac = _sub(key, b"mac v1")
    return hmac.new(mac, b"v1\0" + name.encode("utf-8") + b"\0" + nonce + ct, hashlib.sha256).digest()


def is_sealed(value) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def seal(secret_b32: str, name: str, key: bytes) -> str:
    """The base32 OTP secret of account `name`, sealed: "sealed1:" and base64 of nonce, ciphertext and tag.
    Khoá OTP base32 của tài khoản `name`, đã niêm phong: "sealed1:" và base64 của nonce, bản mã và thẻ."""
    plain = secret_b32.encode("ascii")
    nonce = secrets.token_bytes(NONCE_BYTES)
    ct = bytes(a ^ b for a, b in zip(plain, _keystream(key, nonce, len(plain))))
    return PREFIX + base64.urlsafe_b64encode(nonce + ct + _tag(key, name, nonce, ct)).decode("ascii")


def unseal(value: str, name: str, key: bytes) -> str:
    """The base32 secret inside a sealed value; ValueError when the key, the name or the value is wrong.
    Khoá base32 bên trong một giá trị đã niêm phong; ValueError khi khoá, tên hay giá trị sai."""
    if not is_sealed(value):
        raise ValueError("not a sealed value")
    try:
        raw = base64.urlsafe_b64decode(value[len(PREFIX):].encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        raise ValueError("a sealed value that is not base64") from None
    if len(raw) <= NONCE_BYTES + TAG_BYTES:
        raise ValueError("a sealed value that is too short")
    nonce, ct, tag = raw[:NONCE_BYTES], raw[NONCE_BYTES:-TAG_BYTES], raw[-TAG_BYTES:]
    if not hmac.compare_digest(tag, _tag(key, name, nonce, ct)):
        raise ValueError("the sealed secret of %s does not open with this key" % name)
    return bytes(a ^ b for a, b in zip(ct, _keystream(key, nonce, len(ct)))).decode("ascii")


def stored(secret_b32: str, name: str, key) -> str:
    """What goes into the database for a new secret: sealed when there is a key, as it is when there is none.
    Thứ ghi vào cơ sở dữ liệu cho một khoá mới: niêm phong khi có khoá, để nguyên khi không có."""
    return seal(secret_b32, name, key) if key else secret_b32


def plain(value: str, name: str, key):
    """The base32 secret of a stored value, or None when it is sealed and cannot be opened here.
    Khoá base32 của một giá trị đã lưu, hoặc None khi nó đã niêm phong mà ở đây không mở được."""
    if not is_sealed(value):
        return value
    if not key:
        return None
    try:
        return unseal(value, name, key)
    except ValueError:
        return None
