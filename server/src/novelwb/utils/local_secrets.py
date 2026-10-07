"""DPAPI protection on Windows; permission-restricted local storage elsewhere."""

from __future__ import annotations

import base64
import sys


def protection_method() -> str:
    return "windows-dpapi" if sys.platform == "win32" else "file-permissions"


def _dpapi(data: bytes, *, decrypt: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    function.restype = wintypes.BOOL
    # Current Windows user, never CRYPTPROTECT_LOCAL_MACHINE. No interactive prompts.
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ValueError("无法使用当前 Windows 账户保护或读取密钥，请重新输入密钥")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


def protect(value: str) -> str:
    if not value:
        return ""
    if protection_method() == "windows-dpapi":
        return "dpapi:" + base64.b64encode(_dpapi(value.encode(), decrypt=False)).decode("ascii")
    return "plain:" + value


def reveal(value: str) -> str:
    if not value:
        return ""
    if value.startswith("dpapi:"):
        if sys.platform != "win32":
            raise ValueError("此密钥由 Windows 账户保护；迁移电脑后请重新输入")
        try:
            return _dpapi(base64.b64decode(value[6:], validate=True), decrypt=True).decode()
        except (ValueError, UnicodeError):
            raise ValueError("无法读取已保存密钥，请使用原 Windows 账户或重新输入") from None
    if value.startswith("plain:"):
        return value[6:]
    raise ValueError("密钥存储格式不受支持，请重新输入")
