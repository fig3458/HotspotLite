# -*- coding: utf-8 -*-
"""HotspotLite — lightweight Win10 mobile hotspot helper (no tray)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

APP_NAME = "HotspotLite"
TASK_NAME = "HotspotLiteAutoStart"
CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
CONFIG_PATH = CONFIG_DIR / "config.json"

# Embedded PowerShell: control Win10 Mobile Hotspot via WinRT.
PS_HELPER = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object {
        $_.Name -eq 'AsTask' -and
        $_.IsGenericMethod -and
        $_.GetParameters().Count -eq 1
    } | Select-Object -First 1)

function Await-WinRT($operation, [Type]$resultType) {
    if ($null -eq $operation) { return $null }
    if ($null -eq $resultType) {
        $asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() |
            Where-Object {
                $_.Name -eq 'AsTask' -and
                -not $_.IsGenericMethod -and
                $_.GetParameters().Count -eq 1
            } | Select-Object -First 1
        $task = $asTask.Invoke($null, @($operation))
        $task.Wait(-1) | Out-Null
        if ($task.IsFaulted) { throw $task.Exception.InnerException }
        return $null
    }
    $method = $asTaskGeneric.MakeGenericMethod($resultType)
    $task = $method.Invoke($null, @($operation))
    $task.Wait(-1) | Out-Null
    if ($task.IsFaulted) { throw $task.Exception.InnerException }
    return $task.Result
}

$null = [Windows.Networking.Connectivity.NetworkInformation, Windows.Networking.Connectivity, ContentType = WindowsRuntime]
$null = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager, Windows.Networking.NetworkOperators, ContentType = WindowsRuntime]
$null = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringAccessPointConfiguration, Windows.Networking.NetworkOperators, ContentType = WindowsRuntime]
$null = [Windows.Networking.NetworkOperators.TetheringOperationalState, Windows.Networking.NetworkOperators, ContentType = WindowsRuntime]
$null = [Windows.Networking.NetworkOperators.TetheringOperationStatus, Windows.Networking.NetworkOperators, ContentType = WindowsRuntime]

function Get-TetherManager {
    $profile = [Windows.Networking.Connectivity.NetworkInformation]::GetInternetConnectionProfile()
    if ($null -eq $profile) {
        throw 'No internet connection profile. Connect Ethernet or Wi-Fi first.'
    }
    return [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager]::CreateFromConnectionProfile($profile)
}

$action = $args[0]
try {
    $mgr = Get-TetherManager
    switch ($action) {
        'status' {
            $cfg = $mgr.GetCurrentAccessPointConfiguration()
            $state = $mgr.TetheringOperationalState.ToString()
            $obj = [ordered]@{
                ok = $true
                state = $state
                ssid = $cfg.Ssid
                password = $cfg.Passphrase
                clients = $mgr.ClientCount
            }
            $obj | ConvertTo-Json -Compress
        }
        'start' {
            $state = $mgr.TetheringOperationalState.ToString()
            if ($state -eq 'On') {
                @{ ok = $true; state = 'On'; message = 'already on' } | ConvertTo-Json -Compress
                break
            }
            $result = Await-WinRT ($mgr.StartTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
            $status = $result.Status.ToString()
            if ($status -ne 'Success') {
                throw ("Start failed: $status")
            }
            @{ ok = $true; state = 'On'; message = 'started' } | ConvertTo-Json -Compress
        }
        'stop' {
            $state = $mgr.TetheringOperationalState.ToString()
            if ($state -eq 'Off') {
                @{ ok = $true; state = 'Off'; message = 'already off' } | ConvertTo-Json -Compress
                break
            }
            $result = Await-WinRT ($mgr.StopTetheringAsync()) ([Windows.Networking.NetworkOperators.NetworkOperatorTetheringOperationResult])
            $status = $result.Status.ToString()
            if ($status -ne 'Success') {
                throw ("Stop failed: $status")
            }
            @{ ok = $true; state = 'Off'; message = 'stopped' } | ConvertTo-Json -Compress
        }
        'configure' {
            $ssid = $args[1]
            $pass = $args[2]
            if ([string]::IsNullOrWhiteSpace($ssid)) { throw 'SSID is empty' }
            if ($pass.Length -lt 8 -or $pass.Length -gt 63) { throw 'Password must be 8-63 characters' }
            $cfg = $mgr.GetCurrentAccessPointConfiguration()
            $cfg.Ssid = $ssid
            $cfg.Passphrase = $pass
            Await-WinRT ($mgr.ConfigureAccessPointAsync($cfg)) $null
            @{ ok = $true; message = 'configured'; ssid = $ssid } | ConvertTo-Json -Compress
        }
        default { throw "Unknown action: $action" }
    }
}
catch {
    @{ ok = $false; error = $_.Exception.Message } | ConvertTo-Json -Compress
    exit 1
}
"""


def app_executable() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable
    return str(Path(__file__).resolve())


def load_config() -> dict:
    defaults = {
        "ssid": "",
        "password": "",
        "autostart": False,
        "autostart_delay_sec": 20,
    }
    if not CONFIG_PATH.exists():
        return defaults
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        defaults.update({k: data.get(k, defaults[k]) for k in defaults})
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return defaults


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def _helper_script_path() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = CONFIG_DIR / "_hotspot_helper.ps1"
    # Refresh if missing or content drifted after updates.
    marker = "# HotspotLite helper v2"
    body = marker + "\n" + PS_HELPER.lstrip()
    existing = path.read_text(encoding="utf-8-sig") if path.exists() else None
    if existing != body:
        # BOM helps Windows PowerShell 5.1 parse the file correctly.
        path.write_text(body, encoding="utf-8-sig")
    return path


_ERR_ZH = {
    "No internet connection profile. Connect Ethernet or Wi-Fi first.": "没有可用的互联网连接，请先连接有线或 Wi‑Fi。",
    "SSID is empty": "热点名称不能为空",
    "Password must be 8-63 characters": "密码长度需为 8–63 个字符",
}


def _localize(result: dict) -> dict:
    err = result.get("error")
    if isinstance(err, str):
        for en, zh in _ERR_ZH.items():
            if en in err:
                result = {**result, "error": err.replace(en, zh)}
                break
        if err.startswith("Start failed:"):
            result = {**result, "error": "开启失败: " + err.split(":", 1)[-1].strip()}
        elif err.startswith("Stop failed:"):
            result = {**result, "error": "关闭失败: " + err.split(":", 1)[-1].strip()}
    return result


def run_hotspot(action: str, *extra: str) -> dict:
    script = _helper_script_path()
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        action,
        *extra,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "操作超时"}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

    raw = (proc.stdout or "").strip()
    if not raw:
        err = (proc.stderr or "").strip() or f"退出码 {proc.returncode}"
        return _localize({"ok": False, "error": err})
    # PowerShell may emit warnings before JSON — take last JSON-looking line.
    line = raw.splitlines()[-1]
    try:
        return _localize(json.loads(line))
    except json.JSONDecodeError:
        return _localize({"ok": False, "error": raw})


def is_autostart_enabled() -> bool:
    cmd = [
        "schtasks",
        "/Query",
        "/TN",
        TASK_NAME,
        "/FO",
        "LIST",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return proc.returncode == 0
    except OSError:
        return False


def set_autostart(enabled: bool, delay_sec: int = 20) -> tuple[bool, str]:
    if enabled:
        delay = max(5, min(int(delay_sec), 300))
        return _create_logon_task(app_executable(), delay)

    proc = subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip()
        if msg and "找不到" not in msg and "cannot find" not in msg.lower():
            return False, msg
    return True, "已关闭开机启动"


def _create_logon_task(exe: str, delay_sec: int) -> tuple[bool, str]:
    if getattr(sys, "frozen", False):
        tr = f'"{exe}" --start'
    else:
        tr = f'"{sys.executable}" "{exe}" --start'

    subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )

    mm, ss = divmod(delay_sec, 60)
    delay = f"{mm:02d}:{ss:02d}"
    create = [
        "schtasks",
        "/Create",
        "/TN",
        TASK_NAME,
        "/TR",
        tr,
        "/SC",
        "ONLOGON",
        "/RL",
        "LIMITED",
        "/F",
        "/DELAY",
        delay,
    ]
    proc = subprocess.run(
        create,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "创建开机任务失败").strip()
    return True, f"已设置开机约 {delay_sec} 秒后自动开热点"


def silent_start() -> int:
    cfg = load_config()
    ssid = (cfg.get("ssid") or "").strip()
    password = cfg.get("password") or ""
    if ssid and password:
        result = run_hotspot("configure", ssid, password)
        if not result.get("ok"):
            # Still try to start with existing system config.
            pass
    # Retry a few times in case network is still coming up.
    last_err = "未知错误"
    for _ in range(5):
        result = run_hotspot("start")
        if result.get("ok"):
            return 0
        last_err = result.get("error") or last_err
        import time

        time.sleep(5)
    # Write a tiny log for troubleshooting autostart failures.
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        (CONFIG_DIR / "last_autostart.log").write_text(last_err, encoding="utf-8")
    except OSError:
        pass
    return 1


def silent_stop() -> int:
    result = run_hotspot("stop")
    return 0 if result.get("ok") else 1


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("HotspotLite — Win10 热点")
        self.resizable(False, False)
        self.configure(padx=14, pady=12)

        self.cfg = load_config()
        self.status_var = tk.StringVar(value="正在读取状态…")
        self.ssid_var = tk.StringVar(value=self.cfg.get("ssid") or "")
        self.pass_var = tk.StringVar(value=self.cfg.get("password") or "")
        self.auto_var = tk.BooleanVar(value=bool(self.cfg.get("autostart")) or is_autostart_enabled())
        self.msg_var = tk.StringVar(value="")

        frm = ttk.Frame(self)
        frm.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frm, text="状态").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Label(frm, textvariable=self.status_var).grid(row=0, column=1, columnspan=2, sticky="w", pady=(0, 6))

        ttk.Label(frm, text="热点名称").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.ssid_var, width=28).grid(row=1, column=1, columnspan=2, sticky="we", pady=4)

        ttk.Label(frm, text="密码").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=self.pass_var, width=28, show="•").grid(
            row=2, column=1, columnspan=2, sticky="we", pady=4
        )

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=3, sticky="we", pady=(10, 4))
        ttk.Button(btns, text="开启热点", command=self.on_start).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="关闭热点", command=self.on_stop).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="保存配置", command=self.on_save).pack(side="left")

        ttk.Checkbutton(
            frm,
            text="开机自动开启热点（登录后约 20 秒）",
            variable=self.auto_var,
            command=self.on_autostart_toggle,
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 4))

        ttk.Label(frm, textvariable=self.msg_var, foreground="#333").grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(6, 0)
        )

        tip = ttk.Label(
            frm,
            text="不常驻托盘。勾选开机启动后，登录时静默开热点。",
            foreground="#666",
        )
        tip.grid(row=6, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self.after(100, self.refresh_status)

    def set_msg(self, text: str) -> None:
        self.msg_var.set(text)

    def refresh_status(self) -> None:
        result = run_hotspot("status")
        if not result.get("ok"):
            self.status_var.set("无法读取（需已联网）")
            self.set_msg(result.get("error") or "")
            return
        state = result.get("state") or "?"
        mapping = {"On": "已开启", "Off": "已关闭", "InTransition": "切换中…"}
        clients = result.get("clients", 0)
        self.status_var.set(f"{mapping.get(state, state)} · 已连接 {clients} 台")
        if not self.ssid_var.get() and result.get("ssid"):
            self.ssid_var.set(result["ssid"])
        if not self.pass_var.get() and result.get("password"):
            self.pass_var.set(result["password"])

    def _persist_fields(self) -> None:
        self.cfg["ssid"] = self.ssid_var.get().strip()
        self.cfg["password"] = self.pass_var.get()
        self.cfg["autostart"] = bool(self.auto_var.get())
        save_config(self.cfg)

    def on_save(self) -> None:
        ssid = self.ssid_var.get().strip()
        password = self.pass_var.get()
        if not ssid:
            messagebox.showwarning(APP_NAME, "请填写热点名称")
            return
        if len(password) < 8 or len(password) > 63:
            messagebox.showwarning(APP_NAME, "密码长度需为 8–63 个字符")
            return
        result = run_hotspot("configure", ssid, password)
        if not result.get("ok"):
            messagebox.showerror(APP_NAME, result.get("error") or "保存失败")
            return
        self._persist_fields()
        self.set_msg("配置已保存到系统热点")
        self.refresh_status()

    def on_start(self) -> None:
        ssid = self.ssid_var.get().strip()
        password = self.pass_var.get()
        if ssid and password and len(password) >= 8:
            cfg_result = run_hotspot("configure", ssid, password)
            if not cfg_result.get("ok"):
                self.set_msg(cfg_result.get("error") or "配置失败，仍尝试开启…")
        result = run_hotspot("start")
        if not result.get("ok"):
            messagebox.showerror(APP_NAME, result.get("error") or "开启失败")
            return
        self._persist_fields()
        self.set_msg("热点已开启")
        self.refresh_status()

    def on_stop(self) -> None:
        result = run_hotspot("stop")
        if not result.get("ok"):
            messagebox.showerror(APP_NAME, result.get("error") or "关闭失败")
            return
        self.set_msg("热点已关闭")
        self.refresh_status()

    def on_autostart_toggle(self) -> None:
        enabled = bool(self.auto_var.get())
        ok, msg = set_autostart(enabled, int(self.cfg.get("autostart_delay_sec") or 20))
        if not ok:
            self.auto_var.set(not enabled)
            messagebox.showerror(APP_NAME, msg)
            return
        self.cfg["autostart"] = enabled
        save_config(self.cfg)
        self.set_msg(msg)


def main() -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--start", action="store_true", help="静默开启热点后退出")
    parser.add_argument("--stop", action="store_true", help="静默关闭热点后退出")
    args = parser.parse_args()

    if args.start:
        return silent_start()
    if args.stop:
        return silent_stop()

    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
