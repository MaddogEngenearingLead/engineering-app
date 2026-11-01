"""Tkinter Job Manager: login, dashboard and new-job screens.

Launch with: python -m app.gui

"Create Job" creates <uploads>/<job number>.json and copies the P&ID and scope
into <uploads>/<job number>/pid and /scope. Clicking a job (or its Regenerate
BOM button) runs the BOM scan in the background with a progress bar; the
finished BOM is linked next to the job.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from tkinterdnd2 import DND_FILES, TkinterDnD

from app.job_manager import JobManager
from app.services.accounts import SECURITY_QUESTIONS, AccountError, AccountStore
from app.services.job_scan import run_job_scan
from app.services.updater import (
    UpdateInfo, apply_update, can_self_update, check_for_update, download_update,
)
from app.version import __version__


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
        self.title(f"Job Manager App v{__version__}")
        self.geometry("640x500")
        self.configure(padx=20, pady=20)
        self.jobs = JobManager(get_upload_dir())
        self.accounts = AccountStore(Path(get_upload_dir()).parent)
        self.current_user: str | None = None
        self.running: set[str] = set()
        self.update_info: UpdateInfo | None = None
        self.updating = False
        self.show_login_screen()
        threading.Thread(target=self._check_updates, daemon=True).start()

    def clear_screen(self):
        for widget in self.winfo_children():
            widget.destroy()
        self._render_update_banner()

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------

    def _check_updates(self):
        info = check_for_update()
        if info:
            self.after(0, lambda: self._on_update_found(info))

    def _on_update_found(self, info: UpdateInfo):
        self.update_info = info
        self.refresh_screen()

    def refresh_screen(self):
        # Re-render the current screen so the banner appears; skip the login form
        # to avoid wiping what the user is typing.
        if hasattr(self, "username_entry") and self.username_entry.winfo_exists():
            self._render_update_banner()
        else:
            self.show_dashboard()

    def _render_update_banner(self):
        for widget in self.winfo_children():
            if getattr(widget, "is_update_banner", False):
                widget.destroy()
        if not self.update_info:
            return
        banner = tk.Frame(self, bg="#fff3cd", padx=8, pady=6)
        banner.is_update_banner = True
        text = f"Update available: v{self.update_info.version} (you have v{__version__})"
        tk.Label(banner, text=text, bg="#fff3cd").pack(side="left")
        if self.updating:
            tk.Label(banner, text="Downloading...", bg="#fff3cd", fg="#b36b00").pack(side="right")
        elif can_self_update():
            tk.Button(banner, text="Update now", command=self.start_update,
                      relief="groove").pack(side="right")
        banner.pack(side="top", fill="x", pady=(0, 10), before=self._first_non_banner())

    def _first_non_banner(self):
        for widget in self.pack_slaves():
            if not getattr(widget, "is_update_banner", False):
                return widget
        return None

    def start_update(self):
        if self.updating or not self.update_info:
            return
        if self.running and not messagebox.askyesno(
            "Scan in progress", "A BOM scan is running and will be cancelled. Update anyway?"
        ):
            return
        self.updating = True
        self._render_update_banner()
        info = self.update_info

        def work():
            try:
                path = download_update(info)
                apply_update(path)
            except Exception as exc:
                self.after(0, lambda: self._update_failed(str(exc)))
                return
            self.after(0, self.destroy)

        threading.Thread(target=work, daemon=True).start()

    def _update_failed(self, message: str):
        self.updating = False
        self._render_update_banner()
        messagebox.showerror("Update failed", f"Could not install the update: {message}")

    def show_login_screen(self):
        self.clear_screen()
        tk.Label(self, text="Login", font=("Arial", 18, "bold")).pack(pady=(0, 20))
        tk.Label(self, text="Username:").pack(anchor="w")
        self.username_entry = tk.Entry(self, width=40)
        self.username_entry.pack(pady=5)
        tk.Label(self, text="Password:").pack(anchor="w")
        self.password_entry = tk.Entry(self, width=40, show="*")
        self.password_entry.pack(pady=5)
        self.password_entry.bind("<Return>", lambda _e: self.process_login())
        tk.Button(self, text="Login", command=self.process_login, width=20,
                  bg="#4CAF50", fg="white").pack(pady=15)
        tk.Button(self, text="Create Account", command=self.create_account,
                  relief="flat", fg="blue").pack()
        tk.Button(self, text="Forgot password?", command=self.forgot_password,
                  relief="flat", fg="blue").pack()

    def process_login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        if not username or not password:
            messagebox.showerror("Error", "Please enter both username and password")
            return
        if not self.accounts.has_accounts():
            messagebox.showinfo("No accounts", "No accounts exist yet. Click 'Create Account' first.")
            return
        try:
            self.current_user = self.accounts.authenticate(username, password)
        except AccountError as exc:
            messagebox.showerror("Login failed", str(exc))
            return
        self.show_dashboard()

    def create_account(self):
        AccountWindow(self)

    def forgot_password(self):
        ResetPasswordWindow(self, self.username_entry.get().strip())

    def logout(self):
        self.current_user = None
        self.show_login_screen()

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def show_dashboard(self):
        self.clear_screen()
        header = tk.Frame(self)
        header.pack(fill="x", pady=(0, 10))
        tk.Label(header, text="Dashboard", font=("Arial", 18, "bold")).pack(side="left")
        tk.Button(header, text="Log out", command=self.logout, relief="groove").pack(side="right")
        tk.Label(header, text=f"{self.current_user or ''}  ", fg="gray").pack(side="right")
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
        # The job file (<uploads>/<job>.json) holds the latest BOM links.
        data = self.jobs._load_json(self.jobs.job_file_path(number)) or meta
        is_running = number in self.running

        row = tk.Frame(parent)
        row.pack(fill="x", anchor="w", pady=3)

        link = tk.Label(row, text=f"Job #{number}", fg="blue", cursor="hand2",
                        font=("Arial", 10, "underline"))
        link.pack(side="left")
        link.bind("<Button-1>", lambda _e, n=number: self.start_scan(n))

        if is_running:
            bar = ttk.Progressbar(row, mode="indeterminate", length=110)
            bar.pack(side="left", padx=(10, 4))
            bar.start(12)
            tk.Label(row, text="Generating BOM...", fg="#b36b00").pack(side="left")
            return

        status = data.get("bom_status")
        if status == "completed":
            tk.Label(row, text="  BOM:", fg="gray").pack(side="left")
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
            tk.Label(row, text="  BOM failed", fg="red").pack(side="left")

        tk.Button(row, text="Regenerate BOM", command=lambda n=number: self.start_scan(n),
                  relief="groove").pack(side="right")

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

    def open_new_job_window(self, job_number: str = "", files: dict | None = None):
        NewJobWindow(self, job_number=job_number, files=files)


class AccountWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Create Account")
        self.configure(padx=20, pady=20)
        self.grab_set()
        self.username = self._field("Username:")
        self.password = self._field("Password (min 8 characters):", show="*")
        self.confirm = self._field("Confirm password:", show="*")
        tk.Label(self, text="Security question (used to reset your password):").pack(anchor="w", pady=(10, 0))
        self.question = ttk.Combobox(self, values=SECURITY_QUESTIONS, state="readonly", width=45)
        self.question.current(0)
        self.question.pack(pady=5)
        self.answer = self._field("Answer:")
        tk.Button(self, text="Create Account", command=self.submit, width=20,
                  bg="#4CAF50", fg="white").pack(pady=15)

    def _field(self, label: str, show: str | None = None) -> tk.Entry:
        tk.Label(self, text=label).pack(anchor="w")
        entry = tk.Entry(self, width=48, show=show or "")
        entry.pack(pady=3)
        return entry

    def submit(self):
        if self.password.get() != self.confirm.get():
            messagebox.showerror("Error", "Passwords do not match.", parent=self)
            return
        try:
            self.parent.accounts.create_account(
                self.username.get(), self.password.get(), self.question.get(), self.answer.get()
            )
        except AccountError as exc:
            messagebox.showerror("Error", str(exc), parent=self)
            return
        messagebox.showinfo("Account created", "Account created. You can log in now.", parent=self)
        self.destroy()


class ResetPasswordWindow(tk.Toplevel):
    def __init__(self, parent, username: str = ""):
        super().__init__(parent)
        self.parent = parent
        self.title("Reset Password")
        self.configure(padx=20, pady=20)
        self.grab_set()
        tk.Label(self, text="Username:").pack(anchor="w")
        self.username = tk.Entry(self, width=48)
        self.username.pack(pady=3)
        self.username.insert(0, username)
        tk.Button(self, text="Next", command=self.load_question).pack(pady=5)
        self.step2 = tk.Frame(self)
        self.question_label = tk.Label(self.step2, wraplength=380, justify="left")
        self.question_label.pack(anchor="w")
        self.answer = self._entry("Answer:")
        self.new_password = self._entry("New password (min 8 characters):", show="*")
        self.confirm = self._entry("Confirm new password:", show="*")
        tk.Button(self.step2, text="Reset Password", command=self.submit, width=20,
                  bg="#4CAF50", fg="white").pack(pady=10)

    def _entry(self, label: str, show: str | None = None) -> tk.Entry:
        tk.Label(self.step2, text=label).pack(anchor="w")
        entry = tk.Entry(self.step2, width=48, show=show or "")
        entry.pack(pady=3)
        return entry

    def load_question(self):
        try:
            question = self.parent.accounts.get_question(self.username.get())
        except AccountError as exc:
            messagebox.showerror("Error", str(exc), parent=self)
            return
        self.question_label.config(text=question)
        self.step2.pack(fill="x")

    def submit(self):
        if self.new_password.get() != self.confirm.get():
            messagebox.showerror("Error", "Passwords do not match.", parent=self)
            return
        try:
            self.parent.accounts.reset_password(
                self.username.get(), self.answer.get(), self.new_password.get()
            )
        except AccountError as exc:
            messagebox.showerror("Error", str(exc), parent=self)
            return
        messagebox.showinfo("Password reset", "Password changed. You can log in now.", parent=self)
        self.destroy()


class NewJobWindow(tk.Toplevel):
    def __init__(self, parent, job_number: str = "", files: dict | None = None):
        super().__init__(parent)
        self.parent = parent
        self.title("New Job")
        self.geometry("450x400")
        self.configure(padx=20, pady=20)
        self.files: dict[str, str] = dict(files or {})

        tk.Label(self, text="Job Number:").pack(anchor="w")
        self.job_number_entry = tk.Entry(self, width=40)
        self.job_number_entry.pack(pady=5)
        self.job_number_entry.insert(0, job_number)
        self.job_number_entry.focus_set()

        self.pid_label = self._drop_area("P&ID File", "pid")
        self.scope_label = self._drop_area("Scope File", "scope")

        tk.Button(self, text="Create Job", command=self.submit, width=20,
                  bg="#4CAF50", fg="white").pack(pady=10)

    def _drop_area(self, title: str, key: str) -> tk.Label:
        tk.Label(self, text=f"{title}:").pack(anchor="w", pady=(10, 0))
        current = self.files.get(key)
        area = tk.Label(self, text=current or f"Drag & drop {title} here", relief="groove",
                        bd=2, height=4, bg="#f0f0f0", wraplength=380)
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
        if not job_number:
            # No job number: return to a fresh Create Job screen (dropped files are kept).
            messagebox.showerror("Job number required", "Please enter a job number.")
            files = dict(self.files)
            parent = self.parent
            self.destroy()
            parent.open_new_job_window(files=files)
            return
        if "pid" not in self.files or "scope" not in self.files:
            messagebox.showerror("Error", "Provide both the P&ID file and the Scope file.")
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
