"""Kill child processes automatically when this Python process exits (Windows Job Object).

Without this, closing a console window (instead of pressing Ctrl+C) would leave the
broker / gateway / dashboard children running, and the next start would fail with
"port already in use". With KILL_ON_JOB_CLOSE, Windows terminates every process
assigned to the job when our handle closes, which happens automatically when we exit,
however we exit.
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
from ctypes import wintypes

_JOB = None


def _create_job():
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

    class BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                   "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class EXTENDED(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    handle = k32.CreateJobObjectW(None, None)
    if not handle:
        return None
    info = EXTENDED()
    info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k32.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):  # 9 = ExtendedLimitInformation
        return None
    return k32, handle


def kill_with_parent(proc: subprocess.Popen) -> None:
    """Tie `proc` to this process's lifetime (no-op outside Windows or if the OS refuses)."""
    global _JOB
    if sys.platform != "win32":
        return
    if _JOB is None:
        _JOB = _create_job() or False
    if _JOB:
        k32, handle = _JOB
        k32.AssignProcessToJobObject(handle, wintypes.HANDLE(int(proc._handle)))
