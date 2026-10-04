"""Tkinter Job Manager: login, dashboard and new-job screens.

Launch with: python -m app.gui

"Create Job" creates <uploads>/<job number>/ with the P&ID in pid/ and the
scope file in scope/. The application reads those files back from the paths
recorded in the job's job_metadata.json.
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from tkinterdnd2 import DND_FILES, TkinterDnD

from app.job_manager import JobManager


def get_upload_dir() -> str:
    """Uploads folder used by the GUI.

    Order: UPLOAD_DIR env var, then a per-user folder when running as a
    packaged .exe (Program Files is not writable), else backend/uploads
    (same default as the API).
    """
    env = os.environ.get("UPLOAD_DIR")
    if env:
        return env
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return str(Path(base) / "EngineeringApp" / "uploads")
    return "backend/uploads"


def parse_dropped_files(tk_root, data: str) -> list[str]:
    """Split a tkdnd drop payload (handles paths with spaces) into paths."""
    return list(tk_root.tk.splitlist(data))


class JobManagerApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("Job Manager App")
        self.geometry("500x400")
        self.configure(padx=20, pady=20)
        self.jobs = JobManager(get_upload_dir())
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

    def show_dashboard(self):
        self.clear_screen()
        tk.Label(self, text="Dashboard", font=("Arial", 18, "bold")).pack(pady=(0, 10))
        tk.Button(self, text="+ Start a New Job", command=self.open_new_job_window,
                  width=20, bg="#2196F3", fg="white").pack(pady=10)
        tk.Label(self, text="Your Jobs:", font=("Arial", 12, "bold")).pack(anchor="w", pady=(10, 5))
        jobs_frame = tk.Frame(self)
        jobs_frame.pack(fill="both", expand=True)

        jobs = self.jobs.list_jobs()
        if not jobs:
            tk.Label(jobs_frame, text="No jobs yet. Click '+ Start a New Job'.").pack(anchor="w")
        for meta in jobs:
            number = meta.get("job_number", meta.get("job_safe_name", "?"))
            link = tk.Label(jobs_frame, text=f"Job #{number}", fg="blue", cursor="hand2",
                            font=("Arial", 10, "underline"))
            link.pack(anchor="w", pady=2)
            link.bind("<Button-1>", lambda _e, m=meta: self.show_job_details(m))

    def show_job_details(self, meta: dict):
        messagebox.showinfo(
            "Job",
            f"Job {meta.get('job_number')}\n\n"
            f"Folder: {meta.get('job_dir')}\n"
            f"P&ID: {meta.get('pid_file') or 'none'}\n"
            f"Scope: {meta.get('scope_file') or 'none'}",
        )

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
            metadata = self.parent.jobs.add_job_files(
                job_number, self.files["pid"], self.files["scope"]
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror("Error", f"Could not create job: {exc}")
            return
        messagebox.showinfo(
            "Job Created",
            f"Job {job_number} created.\n\nFolder: {metadata.get('job_dir')}\n"
            f"P&ID: {metadata.get('pid_file')}\nScope: {metadata.get('scope_file')}",
        )
        self.parent.show_dashboard()
        self.destroy()


def main():
    JobManagerApp().mainloop()


if __name__ == "__main__":
    main()
