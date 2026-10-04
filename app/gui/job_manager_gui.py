"""Tkinter Job Manager: login, dashboard and new-job screens.

Launch with: python -m app.gui

"Create Job" creates <uploads>/<job number>.json and copies the P&ID and scope
into <uploads>/<job number>/pid and /scope. Clicking a job on the dashboard runs
the BOM scan in the background; the finished BOM is linked next to the job.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from tkinterdnd2 import DND_FILES, TkinterDnD

from app.job_manager import JobManager
from app.services.job_scan import run_job_scan


def get_upload_dir() -> str:
    """UPLOAD_DIR env var, else a per-user folder when packaged as an .exe
    (Program Files is not writable), else backend/uploads (API default)."""
    env = os.environ.get("UPLOAD_DIR")
    if env:
        return env
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return str(Path(base) / "EngineeringApp" / "uploads")
    return "backend/uploads"


def open_path(path: str) -> None:
    """Open a file with the OS default application."""
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def parse_dropped_files(tk_root, data: str) -> list[str]:
    """Split a tkdnd drop payload (handles paths with spaces) into paths."""
    return list(tk_root.tk.splitlist(data))


class JobManagerApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("Job Manager App")
        self.geometry("560x480")
        self.configure(padx=20, pady=20)
        self.jobs = JobManager(get_upload_dir())
        self.running: set[str] = set()
        self.show_login_screen()

    def clear_screen(self):
        for widget in self.winfo_children():
            widget.destroy()

    def show_login_screen(self):
        self.clear_screen()
        tk.Label(self, text="Login", font=("Arial", 18, "bold")).pack(pady=(0, 20))
        tk.Label(self, text="Username:").pack(anchor="w")
        self.username_entry = tk.Entry(self, width=40)
        self.username_entry.pack(pady=5)
        tk.Label(self, text="Password:").pack(anchor="w")
        self.password_entry = tk.Entry(self, width=40, show="*")
        self.password_entry.pack(pady=5)
        tk.Button(self, text="Login", command=self.process_login, width=20,
                  bg="#4CAF50", fg="white").pack(pady=15)
        tk.Button(self, text="Create Account", command=self.create_account,
                  relief="flat", fg="blue").pack()

    def process_login(self):
        # Placeholder for actual backend authentication
        if self.username_entry.get() and self.password_entry.get():
            self.show_dashboard()
        else:
            messagebox.showerror("Error", "Please enter both username and password")

    def create_account(self):
        messagebox.showinfo("Create Account", "Redirecting to account creation...")

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def show_dashboard(self):
        self.clear_screen()
        tk.Label(self, text="Dashboard", font=("Arial", 18, "bold")).pack(pady=(0, 10))
        tk.Button(self, text="+ Start a New Job", command=self.open_new_job_window,
                  width=20, bg="#2196F3", fg="white").pack(pady=10)
        tk.Label(self, text="Your Jobs (click a job to generate its BOM):",
                 font=("Arial", 12, "bold")).pack(anchor="w", pady=(10, 5))
        jobs_frame = tk.Frame(self)
        jobs_frame.pack(fill="both", expand=True)

        jobs = self.jobs.list_jobs()
        if not jobs:
            tk.Label(jobs_frame, text="No jobs yet. Click '+ Start a New Job'.").pack(anchor="w")
        for meta in jobs:
            self._job_row(jobs_frame, meta)

    def _job_row(self, parent, meta: dict):
        number = meta.get("job_number") or meta.get("job_safe_name") or "?"
        # Prefer the job file (<uploads>/<job>.json): it holds the latest BOM links.
        data = self.jobs._load_json(self.jobs.job_file_path(number)) or meta

        row = tk.Frame(parent)
        row.pack(fill="x", anchor="w", pady=2)

        link = tk.Label(row, text=f"Job #{number}", fg="blue", cursor="hand2",
                        font=("Arial", 10, "underline"))
        link.pack(side="left")
        link.bind("<Button-1>", lambda _e, n=number: self.start_scan(n))

        status = data.get("bom_status")
        if number in self.running or status == "running" and number in self.running:
            tk.Label(row, text="  Generating BOM...", fg="#b36b00").pack(side="left")
        elif status == "completed":
            tk.Label(row, text="   BOM:", fg="gray").pack(side="left")
            for key, label in (("bom_pdf", "PDF"), ("bom_csv", "CSV"), ("bom_json", "JSON")):
                path = data.get(key)
                if path and Path(path).is_file():
                    b = tk.Label(row, text=label, fg="#0a7d2c", cursor="hand2",
                                 font=("Arial", 10, "underline"))
                    b.pack(side="left", padx=(6, 0))
                    b.bind("<Button-1>", lambda _e, p=path: self._open(p))
        elif status == "needs_clarification":
            tk.Label(row, text="  BOM needs review", fg="#b36b00").pack(side="left")
        elif status == "error":
            tk.Label(row, text="  BOM failed (click job to retry)", fg="red").pack(side="left")

    def _open(self, path: str):
        try:
            open_path(path)
        except Exception as exc:
            messagebox.showerror("Error", f"Could not open {path}: {exc}")

    # ------------------------------------------------------------------
    # Background scan
    # ------------------------------------------------------------------

    def start_scan(self, job_number: str):
        if job_number in self.running:
            return
        self.running.add(job_number)
        self.show_dashboard()

        def work():
            outcome = run_job_scan(self.jobs, job_number)
            self.after(0, lambda: self._scan_done(job_number, outcome))

        threading.Thread(target=work, daemon=True).start()

    def _scan_done(self, job_number: str, outcome: dict):
        self.running.discard(job_number)
        self.show_dashboard()
        status = outcome.get("status")
        if status == "completed":
            return  # BOM links now appear next to the job
        title = "BOM needs review" if status == "needs_clarification" else "BOM failed"
        messagebox.showwarning(title, f"Job {job_number}: {outcome.get('message')}")

    def open_new_job_window(self):
        NewJobWindow(self)


class NewJobWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("New Job")
        self.geometry("450x400")
        self.configure(padx=20, pady=20)
        self.files: dict[str, str] = {}

        tk.Label(self, text="Job Number:").pack(anchor="w")
        self.job_number_entry = tk.Entry(self, width=40)
        self.job_number_entry.pack(pady=5)

        self.pid_label = self._drop_area("P&ID File", "pid")
        self.scope_label = self._drop_area("Scope File", "scope")

        tk.Button(self, text="Create Job", command=self.submit, width=20,
                  bg="#4CAF50", fg="white").pack(pady=10)

    def _drop_area(self, title: str, key: str) -> tk.Label:
        tk.Label(self, text=f"{title}:").pack(anchor="w", pady=(10, 0))
        area = tk.Label(self, text=f"Drag & drop {title} here", relief="groove",
                        bd=2, height=4, bg="#f0f0f0")
        area.pack(fill="x", pady=5)
        area.drop_target_register(DND_FILES)
        area.dnd_bind("<<Drop>>", lambda event, k=key, a=area: self._on_drop(event, k, a))
        return area

    def _on_drop(self, event, key: str, area: tk.Label):
        paths = parse_dropped_files(self, event.data)
        if paths:
            self.files[key] = paths[0]
            area.config(text=paths[0])

    def submit(self):
        job_number = self.job_number_entry.get().strip()
        if not job_number or "pid" not in self.files or "scope" not in self.files:
            messagebox.showerror("Error", "Enter a job number and provide both files")
            return
        try:
            data = self.parent.jobs.add_job_files(
                job_number, self.files["pid"], self.files["scope"]
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror("Error", f"Could not create job: {exc}")
            return
        messagebox.showinfo(
            "Job Created",
            f"Job {job_number} created.\n\nJob file: {data.get('job_file')}\n"
            f"P&ID: {data.get('pid_file')}\nScope: {data.get('scope_file')}\n\n"
            "Click the job on the dashboard to generate its BOM.",
        )
        self.parent.show_dashboard()
        self.destroy()


def main():
    JobManagerApp().mainloop()


if __name__ == "__main__":
    main()
