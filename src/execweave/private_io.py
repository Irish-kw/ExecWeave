"""Private, atomic artifact writes for run-local evidence and derived receipts.

The helpers create replacement bytes in the destination directory with owner-only
permissions before publication.  They never write sensitive bytes through a
pre-existing path, so a symlink/hardlink/non-regular destination cannot redirect
or observe the new payload.  POSIX mode 0600 is enforced before rename; Windows
ACL hardening is performed separately by ``harden_private_file`` when available.
"""
from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any



def private_artifact_path(path: str | Path) -> Path:
    """Normalize a writable artifact path without following its final component."""
    raw = Path(path).expanduser()
    return raw.parent.resolve() / raw.name

def _reject_existing_destination(path: Path, *, allow_replace: bool) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError(f"refusing unsafe artifact destination: {path.name}")
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"refusing non-regular artifact destination: {path.name}")
    if getattr(info, "st_nlink", 1) != 1:
        raise ValueError(f"refusing multiply-linked artifact destination: {path.name}")
    if not allow_replace:
        raise FileExistsError(f"ExecWeave artifact already exists: {path}")


def _fsync_parent(path: Path) -> None:
    if os.name == "nt" or not hasattr(os, "O_DIRECTORY"):
        return
    flags = os.O_RDONLY | os.O_DIRECTORY
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path.parent, flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _windows_owner_only_acl(path: Path) -> bool:
    """Best-effort owner-only protected DACL without pywin32.

    This uses the file's current owner SID, converts that SID to SDDL, and applies
    a protected DACL granting only that owner full file access.  Returning False
    means no Windows privacy claim may be made by the caller.
    """
    if os.name != "nt":
        return True
    try:
        import ctypes
        from ctypes import wintypes

        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        SE_FILE_OBJECT = 1
        OWNER_SECURITY_INFORMATION = 0x00000001
        DACL_SECURITY_INFORMATION = 0x00000004
        PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
        SDDL_REVISION_1 = 1

        owner = ctypes.c_void_p()
        old_sd = ctypes.c_void_p()
        get_named = advapi32.GetNamedSecurityInfoW
        get_named.argtypes = [
            wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        ]
        get_named.restype = wintypes.DWORD
        status = get_named(str(path), SE_FILE_OBJECT, OWNER_SECURITY_INFORMATION,
                           ctypes.byref(owner), None, None, None, ctypes.byref(old_sd))
        if status != 0 or not owner.value:
            return False
        try:
            sid_text = wintypes.LPWSTR()
            convert_sid = advapi32.ConvertSidToStringSidW
            convert_sid.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
            convert_sid.restype = wintypes.BOOL
            if not convert_sid(owner, ctypes.byref(sid_text)):
                return False
            try:
                sddl = f"D:P(A;;FA;;;{sid_text.value})"
            finally:
                kernel32.LocalFree(sid_text)

            new_sd = ctypes.c_void_p()
            convert_sd = advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW
            convert_sd.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
            convert_sd.restype = wintypes.BOOL
            if not convert_sd(sddl, SDDL_REVISION_1, ctypes.byref(new_sd), None):
                return False
            try:
                present = wintypes.BOOL()
                dacl = ctypes.c_void_p()
                defaulted = wintypes.BOOL()
                get_dacl = advapi32.GetSecurityDescriptorDacl
                get_dacl.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL),
                                     ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL)]
                get_dacl.restype = wintypes.BOOL
                if not get_dacl(new_sd, ctypes.byref(present), ctypes.byref(dacl),
                                ctypes.byref(defaulted)) or not present.value:
                    return False
                set_named = advapi32.SetNamedSecurityInfoW
                set_named.argtypes = [wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
                                      ctypes.c_void_p, ctypes.c_void_p,
                                      ctypes.c_void_p, ctypes.c_void_p]
                set_named.restype = wintypes.DWORD
                status = set_named(
                    str(path), SE_FILE_OBJECT,
                    DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
                    None, None, dacl, None,
                )
                return status == 0
            finally:
                kernel32.LocalFree(new_sd)
        finally:
            kernel32.LocalFree(old_sd)
    except (AttributeError, OSError, ValueError):
        return False



def _windows_private_acl_state(path: Path) -> str:
    if os.name != "nt":
        return "not_applicable"
    try:
        import ctypes
        from ctypes import wintypes

        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        SE_FILE_OBJECT = 1
        OWNER_SECURITY_INFORMATION = 0x00000001
        DACL_SECURITY_INFORMATION = 0x00000004
        SDDL_REVISION_1 = 1
        owner = ctypes.c_void_p()
        sd = ctypes.c_void_p()
        get_named = advapi32.GetNamedSecurityInfoW
        get_named.argtypes = [
            wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        ]
        get_named.restype = wintypes.DWORD
        if get_named(str(path), SE_FILE_OBJECT, OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION,
                     ctypes.byref(owner), None, None, None, ctypes.byref(sd)) != 0:
            return "unknown"
        try:
            owner_text = wintypes.LPWSTR()
            convert_sid = advapi32.ConvertSidToStringSidW
            convert_sid.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
            convert_sid.restype = wintypes.BOOL
            if not convert_sid(owner, ctypes.byref(owner_text)):
                return "unknown"
            try:
                owner_sid = owner_text.value
            finally:
                kernel32.LocalFree(owner_text)
            text = wintypes.LPWSTR()
            convert_sd = advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW
            convert_sd.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                   ctypes.POINTER(wintypes.LPWSTR), ctypes.c_void_p]
            convert_sd.restype = wintypes.BOOL
            if not convert_sd(sd, SDDL_REVISION_1, DACL_SECURITY_INFORMATION,
                              ctypes.byref(text), None):
                return "unknown"
            try:
                sddl = text.value or ""
            finally:
                kernel32.LocalFree(text)
            # A protected DACL with one allow ACE for the file owner is the contract.
            if sddl.startswith("D:P") and sddl.count("(") == 1 and owner_sid in sddl:
                return "owner_only"
            return "not_private"
        finally:
            kernel32.LocalFree(sd)
    except (AttributeError, OSError, ValueError):
        return "unknown"


def private_file_security_state(path: str | Path) -> str:
    target = Path(path)
    try:
        info = target.lstat()
    except OSError:
        return "unavailable"
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        return "unsafe"
    if os.name == "nt":
        return _windows_private_acl_state(target)
    return "owner_only" if stat.S_IMODE(info.st_mode) == 0o600 else "not_private"

def harden_private_file(path: str | Path) -> bool:
    target = Path(path)
    try:
        info = target.lstat()
    except OSError:
        return False
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        return False
    if os.name != "nt":
        try:
            target.chmod(0o600)
            return stat.S_IMODE(target.stat().st_mode) == 0o600
        except OSError:
            return False
    return _windows_owner_only_acl(target) and private_file_security_state(target) == "owner_only"



def append_private_text(path: str | Path, text: str) -> Path:
    """Append UTF-8 text only after the destination is proven private and regular.

    New files are created empty, hardened before any sensitive bytes are written,
    and then appended under the caller's existing inter-process lock. Existing
    symlinks, reparse points, hardlinks and non-regular files are rejected.
    """
    raw = Path(path).expanduser()
    raw.parent.mkdir(parents=True, exist_ok=True)
    target = private_artifact_path(raw)
    _reject_existing_destination(target, allow_replace=True)
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(target, flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or getattr(info, "st_nlink", 1) != 1:
            raise ValueError(f"refusing non-private append destination: {target.name}")
        # Re-check the directory entry after open on platforms without O_NOFOLLOW.
        entry = target.lstat()
        if stat.S_ISLNK(entry.st_mode) or getattr(entry, "st_file_attributes", 0) & 0x400:
            raise ValueError(f"refusing unsafe artifact destination: {target.name}")
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        if not harden_private_file(target):
            raise OSError("unable to establish private append permissions")
        with os.fdopen(fd, "a", encoding="utf-8", newline="\n", closefd=False) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(fd)
    if private_file_security_state(target) != "owner_only":
        raise OSError("private append permission verification failed")
    return target

def write_private_bytes(
    path: str | Path,
    payload: bytes,
    *,
    replace: bool = False,
) -> Path:
    raw = Path(path).expanduser()
    raw.parent.mkdir(parents=True, exist_ok=True)
    target = private_artifact_path(raw)
    _reject_existing_destination(target, allow_replace=replace)

    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    temp = Path(temporary)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if not harden_private_file(temp):
            raise OSError("unable to establish private artifact permissions")
        # Re-check immediately before publication.  The new sensitive bytes have
        # only ever existed in our private temporary file at this point.
        _reject_existing_destination(target, allow_replace=replace)
        os.replace(temp, target)
        if not harden_private_file(target):
            try:
                target.unlink()
            finally:
                raise OSError("unable to preserve private artifact permissions")
        _fsync_parent(target)
        return target
    finally:
        temp.unlink(missing_ok=True)


def write_private_text(
    path: str | Path,
    text: str,
    *,
    replace: bool = False,
    encoding: str = "utf-8",
) -> Path:
    return write_private_bytes(path, text.encode(encoding), replace=replace)


def write_private_json(
    path: str | Path,
    payload: Any,
    *,
    replace: bool = False,
) -> Path:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return write_private_text(path, rendered, replace=replace)
