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
DEFAULT_IMAGE = "1n3/sn1per:latest"
RESULTS = Path.home() / "ScannerResults" / "Sn1per"


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")
        self.title(APP_TITLE)
        self.geometry("860x680")
        self.minsize(740, 580)
        self.image = DEFAULT_IMAGE
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

        warn = ctk.CTkLabel(
            form,
            text="Only scan systems you own or have written permission to test.",
            text_color="#D29922",
            anchor="w",
        )
        warn.pack(fill="x", pady=(0, 10))

        row = ctk.CTkFrame(form, fg_color="transparent")
        row.pack(fill="x")
        self.btn_setup = ctk.CTkButton(row, text="1. First-time Setup", height=40, command=self.setup)
        self.btn_setup.pack(side="left", padx=(0, 8))
        self.btn_scan = ctk.CTkButton(row, text="2. Start Scan", height=40, fg_color="#238636", command=self.scan)
        self.btn_scan.pack(side="left", padx=(0, 8))
        self.btn_results = ctk.CTkButton(row, text="Open Results", height=40, fg_color="#444C56", command=lambda: docker_util.open_folder(RESULTS))
        self.btn_results.pack(side="left")

        self.status = ctk.CTkLabel(self, text="Ready", text_color="#3FB950", anchor="w")
        self.status.pack(fill="x", padx=24, pady=(12, 0))
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

    def setup(self) -> None:
        def job() -> None:
            log = lambda m: self.after(0, lambda msg=m: self.write(msg))
            self.after(0, lambda: self.set_status("Setting up...", True))
            if not docker_util.ensure_docker(log):
                self.after(0, lambda: self.set_status("Docker needed", False))
                return
            ok = docker_util.ensure_image(self.image, log)
            if not ok:
                alt = "1n3/sn1per"
                log(f"Trying alternate image tag: {alt}")
                ok = docker_util.ensure_image(alt, log)
                if ok:
                    self.image = alt
            self.after(0, lambda: self.set_status("Setup complete" if ok else "Setup failed", ok))
            if ok:
                self.after(0, lambda: messagebox.showinfo(APP_TITLE, "Setup complete. Enter a target and click Start Scan."))

        self._run(job)

    def scan(self) -> None:
        target = self.target.get().strip().removeprefix("https://").removeprefix("http://").split("/")[0]
        if not target:
            messagebox.showwarning(APP_TITLE, "Enter a target first.")
            return
        mode = self.mode.get()
        mode_flag = {
            "Normal": "normal",
            "Stealth": "stealth",
            "Discover": "discover",
            "Port": "port",
        }[mode]

        def job() -> None:
            log = lambda m: self.after(0, lambda msg=m: self.write(msg))
            self.after(0, lambda: self.set_status(f"Scanning {target} ({mode})...", True))
            if not docker_util.ensure_docker(log):
                self.after(0, lambda: self.set_status("Docker needed", False))
                return
            img = self.image
            if not docker_util.image_exists(img):
                if not docker_util.ensure_image(img, log):
                    img = "1n3/sn1per"
                    if not docker_util.ensure_image(img, log):
                        self.after(0, lambda: self.set_status("Setup needed", False))
                        return
                    self.image = img
            out_dir = RESULTS / target.replace(":", "_")
            out_dir.mkdir(parents=True, exist_ok=True)
            # Sn1per loot typically under /usr/share/sniper/loot
            cmd = [
                "docker", "run", "--rm",
                "--network", "host",
                "-v", f"{out_dir}:/usr/share/sniper/loot",
                img,
                "-t", target,
                "-m", mode_flag,
            ]
            # host network can fail on Docker Desktop Windows; fallback without it
            log(f"Sn1per scan started for {target}")
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            assert proc.stdout is not None
            lines = []
            for line in proc.stdout:
                line = line.strip()
                if line:
                    lines.append(line)
                    log(line[:220])
            code = proc.wait()
            if code != 0 and "host" in " ".join(cmd):
                log("Retrying without host networking...")
                cmd = [
                    "docker", "run", "--rm",
                    "-v", f"{out_dir}:/usr/share/sniper/loot",
                    img,
                    "-t", target,
                    "-m", mode_flag,
                ]
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                assert proc.stdout is not None
                for line in proc.stdout:
                    line = line.strip()
                    if line:
                        log(line[:220])
                code = proc.wait()
            self.after(0, lambda: self.set_status("Scan finished", True))
            docker_util.open_folder(out_dir)
            self.after(0, lambda: messagebox.showinfo(APP_TITLE, f"Scan finished for {target}.\nResults folder opened."))

        self._run(job)


if __name__ == "__main__":
    App().mainloop()
