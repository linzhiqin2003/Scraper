"""Pure Python implementation of Zhihu's x-zse-96 signature algorithm.

Reverse-engineered from Zhihu's JSVMP-protected JavaScript.
Reference: https://github.com/xiaoweigege/jsvmp-repository/tree/main/zhihu

Two algorithm versions are provided:
- v_new: SM4 block cipher + CBC mode + custom encoding (current production)
- v_old: Simple XOR + char encoding (legacy, kept as fallback)
"""

import hashlib
import random
from typing import Optional

# Current x-zse-93 version string (algorithm identifier)
X_ZSE_93 = "101_3_3.0"

# ============================================================================
# New version constants (SM4-based)
# ============================================================================

_INIT_STR_NEW = "6fpLRqJO8M/c3jnYxFkUVC4ZIG12SiH=5v0mXDazWBTsuw7QetbKdoPyAl+hN9rgE"

# SM4 round keys (zk)
_ZK = [
    1170614578, 1024848638, 1413669199, -343334464,
    -766094290, -1373058082, -143119608, -297228157,
    1933479194, -971186181, -406453910, 460404854,
    -547427574, -1891326262, -1679095901, 2119585428,
    -2029270069, 2035090028, -1521520070, -5587175,
    -77751101, -2094365853, -1243052806, 1579901135,
    1321810770, 456816404, -1391643889, -229302305,
    330002838, -788960546, 363569021, -1947871109,
]

# SM4 S-box (zb)
_ZB = [
    20, 223, 245, 7, 248, 2, 194, 209, 87, 6, 227, 253, 240, 128, 222, 91,
    237, 9, 125, 157, 230, 93, 252, 205, 90, 79, 144, 199, 159, 197, 186, 167,
    39, 37, 156, 198, 38, 42, 43, 168, 217, 153, 15, 103, 80, 189, 71, 191,
    97, 84, 247, 95, 36, 69, 14, 35, 12, 171, 28, 114, 178, 148, 86, 182,
    32, 83, 158, 109, 22, 255, 94, 238, 151, 85, 77, 124, 254, 18, 4, 26,
    123, 176, 232, 193, 131, 172, 143, 142, 150, 30, 10, 146, 162, 62, 224, 218,
    196, 229, 1, 192, 213, 27, 110, 56, 231, 180, 138, 107, 242, 187, 54, 120,
    19, 44, 117, 228, 215, 203, 53, 239, 251, 127, 81, 11, 133, 96, 204, 132,
    41, 115, 73, 55, 249, 147, 102, 48, 122, 145, 106, 118, 74, 190, 29, 16,
    174, 5, 177, 129, 63, 113, 99, 31, 161, 76, 246, 34, 211, 13, 60, 68,
    207, 160, 65, 111, 82, 165, 67, 169, 225, 57, 112, 244, 155, 51, 236, 200,
    233, 58, 61, 47, 100, 137, 185, 64, 17, 70, 234, 163, 219, 108, 170, 166,
    59, 149, 52, 105, 24, 212, 78, 173, 45, 0, 116, 226, 119, 136, 206, 135,
    175, 195, 25, 92, 121, 208, 126, 139, 3, 75, 141, 21, 130, 98, 241, 40,
    154, 66, 184, 49, 181, 46, 243, 88, 101, 183, 8, 23, 72, 188, 104, 179,
    210, 134, 250, 201, 164, 89, 216, 202, 220, 50, 221, 152, 140, 33, 235, 214,
]

# CBC IV XOR offset
_ARRAY_OFFSET = [48, 53, 57, 48, 53, 51, 102, 55, 100, 49, 53, 101, 48, 49, 100, 55]

# ============================================================================
# Old version constants
# ============================================================================

_INIT_STR_OLD = "RuPtXwxpThIZ0qyz_9fYLCOV8B1mMGKs7UnFHgN3iDaWAJE-Qrk2ecSo6bjd4vl5"


# ============================================================================
# Utility functions (32-bit unsigned integer arithmetic)
# ============================================================================

def _u32(x: int) -> int:
    """Force to 32-bit unsigned integer."""
    return x & 0xFFFFFFFF


def _i32(x: int) -> int:
    """Force to 32-bit signed integer (two's complement)."""
    x = x & 0xFFFFFFFF
    return x - 0x100000000 if x >= 0x80000000 else x


def _rotl(x: int, n: int) -> int:
    """Circular left rotation on 32-bit unsigned integer."""
    x = _u32(x)
    return _u32((x << n) | (x >> (32 - n)))


def _bytes_to_u32(b: list, offset: int) -> int:
    """Read 4 bytes (big-endian) as a 32-bit unsigned integer."""
    return _u32(
        ((b[offset] & 0xFF) << 24)
        | ((b[offset + 1] & 0xFF) << 16)
        | ((b[offset + 2] & 0xFF) << 8)
        | (b[offset + 3] & 0xFF)
    )


def _u32_to_bytes(val: int, buf: list, offset: int) -> None:
    """Write a 32-bit unsigned integer as 4 bytes (big-endian)."""
    val = _u32(val)
    buf[offset] = (val >> 24) & 0xFF
    buf[offset + 1] = (val >> 16) & 0xFF
    buf[offset + 2] = (val >> 8) & 0xFF
    buf[offset + 3] = val & 0xFF


# ============================================================================
# SM4 core functions
# ============================================================================

def _sm4_g(x: int) -> int:
    """SM4 round function G: S-box substitution + linear transform."""
    x = _u32(x)
    t = [0, 0, 0, 0]
    t[0] = _ZB[(x >> 24) & 0xFF]
    t[1] = _ZB[(x >> 16) & 0xFF]
    t[2] = _ZB[(x >> 8) & 0xFF]
    t[3] = _ZB[x & 0xFF]

    r = _u32((t[0] << 24) | (t[1] << 16) | (t[2] << 8) | t[3])
    return _u32(r ^ _rotl(r, 2) ^ _rotl(r, 10) ^ _rotl(r, 18) ^ _rotl(r, 24))


def _sm4_encrypt_block(data_16: list) -> list:
    """Encrypt one 16-byte block using SM4.

    Corresponds to JS function `array_0_16_offset(e)`.
    """
    result = [0] * 16
    n = [0] * 36

    n[0] = _bytes_to_u32(data_16, 0)
    n[1] = _bytes_to_u32(data_16, 4)
    n[2] = _bytes_to_u32(data_16, 8)
    n[3] = _bytes_to_u32(data_16, 12)

    for r in range(32):
        rk = _i32(_ZK[r])
        o = _sm4_g(_u32(n[r + 1] ^ n[r + 2] ^ n[r + 3] ^ _u32(rk)))
        n[r + 4] = _u32(n[r] ^ o)

    _u32_to_bytes(n[35], result, 0)
    _u32_to_bytes(n[34], result, 4)
    _u32_to_bytes(n[33], result, 8)
    _u32_to_bytes(n[32], result, 12)

    return result


def _sm4_cbc_encrypt(data: list, iv: list) -> list:
    """Encrypt data using SM4-CBC mode.

    Corresponds to JS function `array_16_48_offset(e, t)`.
    """
    result = []
    length = len(data)
    block_idx = 0

    while length > 0:
        block = data[16 * block_idx: 16 * (block_idx + 1)]
        xored = [(block[c] ^ iv[c]) & 0xFF for c in range(16)]
        iv = _sm4_encrypt_block(xored)
        result.extend(iv)
        block_idx += 1
        length -= 16

    return result


def _encode_first_block(block_16: list) -> list:
    """Encode the first 16-byte block with the offset XOR and encryption.

    Corresponds to JS function `encode_0_16(array_0_16)`.
    """
    result = []
    for i in range(len(block_16)):
        a = (block_16[i] ^ _ARRAY_OFFSET[i]) & 0xFF
        b = (a ^ 42) & 0xFF
        result.append(b)
    return _sm4_encrypt_block(result)


def _base64_encode_triple(ar: list) -> list:
    """Encode 3 bytes into 4 base64-like indices.

    Corresponds to JS function `encode(ar)`.
    """
    b = (ar[1] & 0xFF) << 8
    c = (ar[0] & 0xFF) | b
    d = (ar[2] & 0xFF) << 16
    e = c | d
    result = [e & 63]
    shift = 6
    while len(result) < 4:
        result.append((e >> shift) & 63)
        shift += 6
    return result


# ============================================================================
# Public API
# ============================================================================

def encrypt_md5_new(md5_hex: str, _rand_byte: Optional[int] = None) -> str:
    """Encrypt an MD5 hex string using the new SM4-based algorithm.

    This is the current production algorithm.

    Args:
        md5_hex: 32-character lowercase hex MD5 digest.
        _rand_byte: Internal testing parameter. Do not use.

    Returns:
        Encrypted string (44 characters).
    """
    # Build 48-byte input array
    init_array = []
    for ch in md5_hex:
        init_array.append(ord(ch))

    # Prepend: [random_byte, 0x00, ...md5_chars...]
    init_array.insert(0, 0)
    rand_val = _rand_byte if _rand_byte is not None else random.randint(0, 126)
    init_array.insert(0, rand_val)

    # Pad to 48 bytes
    while len(init_array) < 48:
        init_array.append(14)

    # Split into blocks and encrypt
    block_0_16 = _encode_first_block(init_array[:16])
    block_16_48 = _sm4_cbc_encrypt(init_array[16:48], block_0_16)
    full_array = block_0_16 + block_16_48

    # XOR every 4th byte (from end) with 58
    for i in range(47, -1, -4):
        full_array[i] = (full_array[i] ^ 58) & 0xFF

    # Reverse
    full_array.reverse()

    # Base64-like encoding
    result_indices = []
    for j in range(3, len(full_array) + 1, 3):
        triple = full_array[j - 3: j]
        result_indices.extend(_base64_encode_triple(triple))

    return "".join(_INIT_STR_NEW[idx] for idx in result_indices)


def encrypt_md5_old(md5_hex: str) -> str:
    """Encrypt an MD5 hex string using the old simple algorithm.

    Kept as fallback in case the new version changes.

    Args:
        md5_hex: 32-character lowercase hex MD5 digest.

    Returns:
        Encrypted string (44 characters).
    """
    md5_with_null = md5_hex + "\x00"
    array1 = []

    # Reverse iterate and XOR every 4th
    for i in range(len(md5_hex), -1, -1):
        charcode = ord(md5_with_null[i]) if i < len(md5_with_null) else 0
        if i % 4 == 0:
            charcode ^= 42
        array1.append(charcode)

    # Encode in groups of 3
    result_indices = []
    for j in range(3, len(array1) + 1, 3):
        triple = array1[j - 3: j]
        result_indices.extend(_base64_encode_triple(triple))

    return "".join(_INIT_STR_OLD[idx] for idx in result_indices)


def generate_x_zse_96(
    x_zse_93: str,
    api_path: str,
    d_c0: str,
    x_zst_81: str = "",
    version: str = "new",
) -> str:
    """Generate the x-zse-96 signature header value.

    Args:
        x_zse_93: The x-zse-93 version string (e.g., "101_3_3.0").
        api_path: API URL path with query string
                  (e.g., "/api/v4/search_v3?t=general&q=test").
        d_c0: The d_c0 cookie value (URL-decoded, without quotes).
        x_zst_81: The x-zst-81 header value (often empty).
        version: Algorithm version - "new" (SM4) or "old" (simple).

    Returns:
        Complete x-zse-96 header value (e.g., "2.0_Abc...xyz").
    """
    # Build plaintext: version + path + d_c0 [+ x_zst_81]
    parts = [x_zse_93, api_path, d_c0]
    if x_zst_81:
        parts.append(x_zst_81)
    plaintext = "+".join(parts)

    # MD5 hash
    md5_hex = hashlib.md5(plaintext.encode("utf-8")).hexdigest()

    # Encrypt
    if version == "old":
        encrypted = encrypt_md5_old(md5_hex)
    else:
        encrypted = encrypt_md5_new(md5_hex)

    return f"2.0_{encrypted}"
