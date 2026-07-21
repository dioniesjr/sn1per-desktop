"""Sn1per Desktop - automated pentest GUI (no terminal needed)."""
from __future__ import annotations

import os
import subprocess
import threading
import tkinter.messagebox as messagebox
from pathlib import Path

import customtkinter as ctk

import docker_util

APP_TITLE = "Sn1per Desktop"
LOCAL_IMAGE = "sn1per-desktop:local"
PULL_IMAGE = "xer0dayz/sn1per:latest"
RESULTS = Path.home() / "ScannerResults" / "Sn1per"
ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor" / "Sn1per"


def _hidden_popen(cmd: list[str], cwd: Path | None = None):
    return subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")
        self.title(APP_TITLE)
        self.geometry("860x700")
        self.minsize(740, 580)
        self.image = LOCAL_IMAGE if docker_util.image_exists(LOCAL_IMAGE) else PULL_IMAGE
        RESULTS.mkdir(parents=True, exist_ok=True)

        ctk.CTkLabel(self, text="Sn1per Desktop", font=ctk.CTkFont(size=28, weight="bold")).pack(
            padx=24, pady=(22, 4), anchor="w"
        )
        ctk.CTkLabel(
            self,
            text="One-click automated penetration testing suite. Point at a target and run.",
            text_color="#A0A8B5",
        ).pack(padx=24, pady=(0, 16), anchor="w")

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="x", padx=24)
        ctk.CTkLabel(form, text="Target (domain or IP)", anchor="w").pack(fill="x")
        self.target = ctk.CTkEntry(form, height=42, placeholder_text="example.com")
        self.target.pack(fill="x", pady=(4, 12))

        ctk.CTkLabel(form, text="Scan mode", anchor="w").pack(fill="x")
        self.mode = ctk.CTkSegmentedButton(form, values=["Normal", "Stealth", "Discover", "Port"])
        self.mode.set("Normal")
        self.mode.pack(fill="x", pady=(4, 12))

        ctk.CTkLabel(
            form,
            text="Only scan systems you own or have written permission to test.",
            text_color="#D29922",
            anchor="w",
        ).pack(fill="x", pady=(0, 10))

        row = ctk.CTkFrame(form, fg_color="transparent")
        row.pack(fill="x")
        self.btn_setup = ctk.CTkButton(row, text="1. First-time Setup", height=40, command=self.setup)
        self.btn_setup.pack(side="left", padx=(0, 8))
        self.btn_scan = ctk.CTkButton(row, text="2. Start Scan", height=40, fg_color="#238636", command=self.scan)
        self.btn_scan.pack(side="left", padx=(0, 8))
        self.btn_results = ctk.CTkButton(
            row, text="Open Results", height=40, fg_color="#444C56", command=lambda: docker_util.open_folder(RESULTS)
        )
        self.btn_results.pack(side="left")

        ctk.CTkLabel(
            self,
            text="First-time Setup may take a while (builds Sn1per). Leave this window open.",
            text_color="#8B949E",
        ).pack(padx=24, pady=(10, 4), anchor="w")

        self.status = ctk.CTkLabel(self, text="Ready", text_color="#3FB950", anchor="w")
        self.status.pack(fill="x", padx=24)
        self.progress = ctk.CTkProgressBar(self)
        self.progress.pack(fill="x", padx=24, pady=(6, 6))
        self.progress.set(0)
        self.log = ctk.CTkTextbox(self)
        self.log.pack(fill="both", expand=True, padx=24, pady=(8, 24))
        self._busy = False
        self.after(200, lambda: (self.write("Welcome to Sn1per Desktop."), self.write(f"Results: {RESULTS}")))

    def write(self, msg: str) -> None:
        self.log.insert("end", msg + "\n")
        self.log.see("end")

    def set_status(self, text: str, ok: bool = True) -> None:
        self.status.configure(text=text, text_color="#3FB950" if ok else "#F85149")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        for b in (self.btn_setup, self.btn_scan, self.btn_results):
            b.configure(state=state)
        if busy:
            self.progress.configure(mode="indeterminate")
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self.progress.set(0)

    def _run(self, fn) -> None:
        if self._busy:
            return
        self._set_busy(True)

        def worker() -> None:
            try:
                fn()
            finally:
                self.after(0, lambda: self._set_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def _stream(self, cmd: list[str], log, cwd: Path | None = None) -> int:
        proc = _hidden_popen(cmd, cwd=cwd)
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if line:
                log(line[:220])
        return proc.wait()

    def setup(self) -> None:
        def job() -> None:
            log = lambda m: self.after(0, lambda msg=m: self.write(msg))
            self.after(0, lambda: self.set_status("Setting up...", True))
            if not docker_util.ensure_docker(log):
                self.after(0, lambda: self.set_status("Docker needed", False))
                return

            # Fast path: public image
            if docker_util.ensure_image(PULL_IMAGE, log):
                self.image = PULL_IMAGE
                self.after(0, lambda: self.set_status("Setup complete", True))
                self.after(0, lambda: messagebox.showinfo(APP_TITLE, "Setup complete. Enter a target and click Start Scan."))
                return

            log("Public image unavailable. Building Sn1per from official source (this can take a long time)...")
            VENDOR.parent.mkdir(parents=True, exist_ok=True)
            if not (VENDOR / "Dockerfile").exists():
                if VENDOR.exists():
                    import shutil

                    shutil.rmtree(VENDOR, ignore_errors=True)
                code = self._stream(
                    ["git", "clone", "--depth", "1", "https://github.com/1N3/Sn1per.git", str(VENDOR)],
                    log,
                )
                if code != 0:
                    self.after(0, lambda: self.set_status("Setup failed (clone)", False))
                    return
            code = self._stream(["docker", "build", "-t", LOCAL_IMAGE, "."], log, cwd=VENDOR)
            if code != 0:
                self.after(0, lambda: self.set_status("Setup failed (build)", False))
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        APP_TITLE,
                        "Could not build Sn1per image.\nKeep Docker Desktop open and try First-time Setup again.",
                    ),
                )
                return
            self.image = LOCAL_IMAGE
            self.after(0, lambda: self.set_status("Setup complete", True))
            self.after(0, lambda: messagebox.showinfo(APP_TITLE, "Setup complete. Enter a target and click Start Scan."))

        self._run(job)

    def scan(self) -> None:
        target = self.target.get().strip().removeprefix("https://").removeprefix("http://").split("/")[0]
        if not target:
            messagebox.showwarning(APP_TITLE, "Enter a target first.")
            return
        mode = self.mode.get()
        mode_flag = {"Normal": "normal", "Stealth": "stealth", "Discover": "discover", "Port": "port"}[mode]

        def job() -> None:
            log = lambda m: self.after(0, lambda msg=m: self.write(msg))
            self.after(0, lambda: self.set_status(f"Scanning {target} ({mode})...", True))
            if not docker_util.ensure_docker(log):
                self.after(0, lambda: self.set_status("Docker needed", False))
                return

            img = self.image
            if not docker_util.image_exists(img):
                self.after(0, lambda: self.set_status("Click First-time Setup first", False))
                return

            out_dir = RESULTS / target.replace(":", "_")
            out_dir.mkdir(parents=True, exist_ok=True)
            log(f"Sn1per scan started for {target}")

            # Try common invocation styles for Sn1per containers
            attempts = [
                ["docker", "run", "--rm", "--privileged", "-v", f"{out_dir}:/usr/share/sniper/loot", img, "sniper", "-t", target, "-m", mode_flag],
                ["docker", "run", "--rm", "--privileged", "-v", f"{out_dir}:/usr/share/sniper/loot", img, "/bin/bash", "-lc", f"sniper -t {target} -m {mode_flag}"],
                ["docker", "run", "--rm", "--privileged", "-v", f"{out_dir}:/loot", img, "sniper", "-t", target, "-m", mode_flag],
            ]
            code = 1
            for cmd in attempts:
                log("Running scan...")
                code = self._stream(cmd, log)
                if code == 0:
                    break
                log("Trying alternate launch style...")

            self.after(0, lambda: self.set_status("Scan finished", True))
            docker_util.open_folder(out_dir)
            self.after(0, lambda: messagebox.showinfo(APP_TITLE, f"Scan finished for {target}.\nResults folder opened."))

        self._run(job)


if __name__ == "__main__":
    App().mainloop()
