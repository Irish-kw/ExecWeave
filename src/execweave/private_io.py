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


def _windows_current_user_sid_text() -> str | None:
    """Return the current process user SID, never a group/file-owner surrogate."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class SID_AND_ATTRIBUTES(ctypes.Structure):
            _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]

        class TOKEN_USER(ctypes.Structure):
            _fields_ = [("User", SID_AND_ATTRIBUTES)]

        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        TOKEN_QUERY = 0x0008
        TOKEN_USER_CLASS = 1
        ERROR_INSUFFICIENT_BUFFER = 122

        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p

        open_token = advapi32.OpenProcessToken
        open_token.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        open_token.restype = wintypes.BOOL
        get_token = advapi32.GetTokenInformation
        get_token.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        get_token.restype = wintypes.BOOL
        convert_sid = advapi32.ConvertSidToStringSidW
        convert_sid.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
        convert_sid.restype = wintypes.BOOL

        token = wintypes.HANDLE()
        if not open_token(kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)):
            return None
        try:
            required = wintypes.DWORD()
            get_token(token, TOKEN_USER_CLASS, None, 0, ctypes.byref(required))
            if ctypes.get_last_error() != ERROR_INSUFFICIENT_BUFFER or not required.value:
                return None
            buffer = ctypes.create_string_buffer(required.value)
            if not get_token(
                token,
                TOKEN_USER_CLASS,
                buffer,
                required.value,
                ctypes.byref(required),
            ):
                return None
            token_user = ctypes.cast(buffer, ctypes.POINTER(TOKEN_USER)).contents
            sid_text = wintypes.LPWSTR()
            if not convert_sid(token_user.User.Sid, ctypes.byref(sid_text)):
                return None
            try:
                return sid_text.value or None
            finally:
                kernel32.LocalFree(ctypes.cast(sid_text, ctypes.c_void_p))
        finally:
            kernel32.CloseHandle(token)
    except (AttributeError, OSError, ValueError):
        return None


def _windows_owner_only_acl(path: Path) -> bool:
    """Install a protected DACL granting only the current process user full access."""
    if os.name != "nt":
        return True
    user_sid = _windows_current_user_sid_text()
    if not user_sid:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        SE_FILE_OBJECT = 1
        DACL_SECURITY_INFORMATION = 0x00000004
        PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
        SDDL_REVISION_1 = 1

        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        new_sd = ctypes.c_void_p()
        convert_sd = advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW
        convert_sd.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_void_p,
        ]
        convert_sd.restype = wintypes.BOOL
        if not convert_sd(
            f"D:P(A;;FA;;;{user_sid})",
            SDDL_REVISION_1,
            ctypes.byref(new_sd),
            None,
        ):
            return False
        try:
            present = wintypes.BOOL()
            dacl = ctypes.c_void_p()
            defaulted = wintypes.BOOL()
            get_dacl = advapi32.GetSecurityDescriptorDacl
            get_dacl.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(wintypes.BOOL),
                ctypes.POINTER(ctypes.c_void_p),
                ctypes.POINTER(wintypes.BOOL),
            ]
            get_dacl.restype = wintypes.BOOL
            if not get_dacl(
                new_sd,
                ctypes.byref(present),
                ctypes.byref(dacl),
                ctypes.byref(defaulted),
            ) or not present.value or not dacl.value:
                return False
            set_named = advapi32.SetNamedSecurityInfoW
            set_named.argtypes = [
                wintypes.LPWSTR,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
            ]
            set_named.restype = wintypes.DWORD
            status = set_named(
                str(path),
                SE_FILE_OBJECT,
                DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
                None,
                None,
                dacl,
                None,
            )
            return status == 0
        finally:
            kernel32.LocalFree(new_sd)
    except (AttributeError, OSError, ValueError):
        return False


def _windows_private_acl_state(path: Path) -> str:
    """Verify the protected DACL structurally instead of comparing rendered SDDL."""
    if os.name != "nt":
        return "not_applicable"
    user_sid = _windows_current_user_sid_text()
    if not user_sid:
        return "unknown"
    try:
        import ctypes
        from ctypes import wintypes

        class ACL_SIZE_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("AceCount", wintypes.DWORD),
                ("AclBytesInUse", wintypes.DWORD),
                ("AclBytesFree", wintypes.DWORD),
            ]

        class ACE_HEADER(ctypes.Structure):
            _fields_ = [
                ("AceType", ctypes.c_ubyte),
                ("AceFlags", ctypes.c_ubyte),
                ("AceSize", wintypes.WORD),
            ]

        class ACCESS_ALLOWED_ACE(ctypes.Structure):
            _fields_ = [
                ("Header", ACE_HEADER),
                ("Mask", wintypes.DWORD),
                ("SidStart", wintypes.DWORD),
            ]

        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        SE_FILE_OBJECT = 1
        DACL_SECURITY_INFORMATION = 0x00000004
        ACL_SIZE_INFORMATION_CLASS = 2
        ACCESS_ALLOWED_ACE_TYPE = 0x00
        SE_DACL_PROTECTED = 0x1000
        FILE_ALL_ACCESS = 0x001F01FF

        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        dacl = ctypes.c_void_p()
        sd = ctypes.c_void_p()
        get_named = advapi32.GetNamedSecurityInfoW
        get_named.argtypes = [
            wintypes.LPWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        get_named.restype = wintypes.DWORD
        if get_named(
            str(path),
            SE_FILE_OBJECT,
            DACL_SECURITY_INFORMATION,
            None,
            None,
            ctypes.byref(dacl),
            None,
            ctypes.byref(sd),
        ) != 0 or not dacl.value or not sd.value:
            return "unknown"
        try:
            control = wintypes.WORD()
            revision = wintypes.DWORD()
            get_control = advapi32.GetSecurityDescriptorControl
            get_control.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(wintypes.WORD),
                ctypes.POINTER(wintypes.DWORD),
            ]
            get_control.restype = wintypes.BOOL
            if not get_control(sd, ctypes.byref(control), ctypes.byref(revision)):
                return "unknown"
            if not (control.value & SE_DACL_PROTECTED):
                return "not_private"

            acl_info = ACL_SIZE_INFORMATION()
            get_acl_info = advapi32.GetAclInformation
            get_acl_info.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                wintypes.DWORD,
                ctypes.c_int,
            ]
            get_acl_info.restype = wintypes.BOOL
            if not get_acl_info(
                dacl,
                ctypes.byref(acl_info),
                ctypes.sizeof(acl_info),
                ACL_SIZE_INFORMATION_CLASS,
            ):
                return "unknown"
            if acl_info.AceCount != 1:
                return "not_private"

            ace_ptr = ctypes.c_void_p()
            get_ace = advapi32.GetAce
            get_ace.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
            get_ace.restype = wintypes.BOOL
            if not get_ace(dacl, 0, ctypes.byref(ace_ptr)) or not ace_ptr.value:
                return "unknown"
            ace = ctypes.cast(ace_ptr, ctypes.POINTER(ACCESS_ALLOWED_ACE)).contents
            if ace.Header.AceType != ACCESS_ALLOWED_ACE_TYPE:
                return "not_private"
            if (ace.Mask & FILE_ALL_ACCESS) != FILE_ALL_ACCESS:
                return "not_private"

            convert_sid = advapi32.ConvertSidToStringSidW
            convert_sid.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
            convert_sid.restype = wintypes.BOOL
            ace_sid_ptr = ctypes.c_void_p(
                ace_ptr.value + ACCESS_ALLOWED_ACE.SidStart.offset
            )
            ace_sid_text = wintypes.LPWSTR()
            if not convert_sid(ace_sid_ptr, ctypes.byref(ace_sid_text)):
                return "unknown"
            try:
                return "owner_only" if ace_sid_text.value == user_sid else "not_private"
            finally:
                kernel32.LocalFree(ctypes.cast(ace_sid_text, ctypes.c_void_p))
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