"""Tkinter Job Manager: dashboard, new-job and BOM review screens (local, no login).

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
import webbrowser
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from tkinterdnd2 import DND_FILES, TkinterDnD

from app.job_manager import JobManager
from app.gui.review_window import LocationViewer, ReviewWindow
from app.gui.scrolling import ScrollFrame
from app.gui.help_content import HELP_SECTIONS, PROVIDER_HELP, provider_guidance
from app.services.job_scan import load_current_clarification, run_job_scan
from app.services.review_questions import build_questions
from app.services.scope_work import approve_scope_draft, load_scope_draft
from app.services.updater import (
    UpdateInfo, apply_update, can_self_update, check_for_update, check_for_update_status, download_update,
)
from app.version import __version__


PORTABLE_DIR_NAME = "Jobs"


def _on_removable_drive(path: Path) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        root = path.resolve().anchor
        return ctypes.windll.kernel32.GetDriveTypeW(root) == 2  # DRIVE_REMOVABLE
    except Exception:
        return False


def portable_upload_dir() -> Path | None:
    """A `Jobs` folder next to the exe, used when the exe runs from a USB drive (or the
    user created that folder). Jobs then travel with the program."""
    if not getattr(sys, "frozen", False) or sys.platform == "darwin":
        return None
    exe_dir = Path(sys.executable).resolve().parent
    jobs = exe_dir / PORTABLE_DIR_NAME
    if jobs.is_dir() or _on_removable_drive(exe_dir):
        try:
            jobs.mkdir(exist_ok=True)
            probe = jobs / ".write_test"
            probe.write_text("x")
            probe.unlink()
            return jobs
        except OSError:
            return None
    return None


def get_upload_dir() -> str:
    """UPLOAD_DIR env var, else a `Jobs` folder beside the exe when run from a USB drive
    (or when that folder exists), else a per-user folder when packaged, else backend/uploads."""
    env = os.environ.get("UPLOAD_DIR")
    if env:
        return env
    portable = portable_upload_dir()
    if portable:
        return str(portable)
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
        self.scroller = ScrollFrame(self, padx=20, pady=20)
        self.scroller.pack(side="bottom", fill="both", expand=True)
        self.body = self.scroller.body
        self.jobs = JobManager(get_upload_dir())
        self.running: set[str] = set()
        self.update_info: UpdateInfo | None = None
        self.updating = False
        self.show_dashboard()
        threading.Thread(target=self._check_updates, daemon=True).start()

    def clear_screen(self):
        for widget in self.body.winfo_children():
            widget.destroy()
        self._render_update_banner()

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------

    def _check_updates(self):
        info = check_for_update()
        if info:
            self.after(0, lambda: self._on_update_found(info))

    def check_updates_manually(self):
        def work():
            info, message = check_for_update_status()
            def done():
                if info:
                    self.update_info = info
                    self.refresh_screen()
                messagebox.showinfo("Check for updates", message)
            self.after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def _on_update_found(self, info: UpdateInfo):
        self.update_info = info
        self.refresh_screen()

    def refresh_screen(self):
        # Re-render the current screen so the banner appears
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
        banner.pack(side="top", fill="x", padx=20, pady=(10, 0), before=self.scroller)

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

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def show_dashboard(self):
        self.clear_screen()
        header = tk.Frame(self.body)
        header.pack(fill="x", pady=(0, 10))
        tk.Label(header, text="Dashboard", font=("Arial", 18, "bold")).pack(side="left")
        tk.Button(header, text="Help", command=lambda: HelpWindow(self),
                  relief="groove").pack(side="right", padx=(0, 6))
        tk.Button(header, text="AI settings", command=lambda: AISettingsWindow(self),
                  relief="groove").pack(side="right", padx=(0, 6))
        tk.Button(header, text="Check for updates", command=self.check_updates_manually,
                  relief="groove").pack(side="right")
        tk.Button(self.body, text="+ Start a New Job", command=self.open_new_job_window,
                  width=20, bg="#2196F3", fg="white").pack(pady=10)
        tk.Label(self.body, text="Your Jobs (click a job to generate its BOM):",
                 font=("Arial", 12, "bold")).pack(anchor="w", pady=(10, 5))
        jobs_frame = tk.Frame(self.body)
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
            for key, label in (("bom_pdf", "PDF"),):
                path = data.get(key)
                if path and Path(path).is_file():
                    b = tk.Label(row, text=label, fg="#0a7d2c", cursor="hand2",
                                 font=("Arial", 10, "underline"))
                    b.pack(side="left", padx=(6, 0))
                    b.bind("<Button-1>", lambda _e, p=path: self._open(p))
        elif status == "needs_clarification":
            tk.Label(row, text="  Scan needs clarification", fg="#b36b00").pack(side="left")
            tk.Button(row, text="Choose pages", relief="groove",
                      command=lambda n=number: self.choose_pages(n)).pack(side="left", padx=6)
            tk.Button(row, text="View drawing issues", relief="groove",
                      command=lambda n=number: self.review_scan_issues(n)).pack(side="left", padx=6)
        elif status == "needs_scope_review":
            tk.Label(row, text="  Scope review needed", fg="#b36b00").pack(side="left")
            tk.Button(row, text="Review scope", relief="groove",
                      command=lambda n=number: self.review_scope(n)).pack(side="left", padx=6)
        elif status == "scope_approved":
            tk.Label(row, text="  Scope approved; regenerate BOM", fg="#b36b00").pack(side="left")
        elif status == "error":
            tk.Label(row, text="  BOM failed", fg="red").pack(side="left")

        if status == "completed":
            tk.Button(row, text="Review / clarify", relief="groove",
                      command=lambda n=number: self.open_review(n)).pack(side="right", padx=(0, 6))
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

    def open_review(self, job_number: str):
        ReviewWindow(self, self.jobs, job_number, on_saved=self.show_dashboard)

    def review_scan_issues(self, job_number: str):
        review = load_current_clarification(self.jobs, job_number)
        if not review:
            messagebox.showinfo("Drawing issues", "No scan issues are available.", parent=self)
            return
        flags = review.get("result", {}).get("questions", [])
        questions = build_questions([{**f, "severity": f.get("severity", "review")} for f in flags], [])
        questions = [q for q in questions if q.get("locations")]
        if not questions:
            messagebox.showinfo("Drawing issues", "No drawing locations are available for these issues.",
                                parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title(f"Drawing issues - Job #{job_number}")
        tk.Label(dialog, text="Select an issue to inspect its drawing location.").pack(anchor="w", padx=10, pady=5)
        listing = tk.Listbox(dialog, width=100, height=min(10, len(questions)))
        listing.pack(fill="both", expand=True, padx=10, pady=5)
        for q in questions:
            listing.insert("end", q["question"])
        listing.selection_set(0)

        def show():
            selection = listing.curselection()
            if not selection:
                return
            q = questions[selection[0]]
            try:
                LocationViewer(dialog, review["pid_file"], q["title"], q["locations"], question=q)
            except Exception as exc:
                messagebox.showerror("Drawing issues", f"Could not open the drawing: {exc}", parent=dialog)

        tk.Button(dialog, text="Show on drawing", command=show).pack(pady=5)

    def review_scope(self, job_number: str):
        try:
            draft = load_scope_draft(self.jobs, job_number)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Scope review", str(exc), parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title(f"Review proposed scope - Job #{job_number}")
        dialog.geometry("800x600")
        tk.Label(dialog, text="Edit and approve the scope before it is saved. Drawing notes and listed "
                 "items are evidence, not proof of authorized work; verify against the P&ID.",
                 wraplength=760, justify="left").pack(fill="x", padx=12, pady=10)
        text = tk.Text(dialog, wrap="word")
        text.pack(fill="both", expand=True, padx=12, pady=5)
        text.insert("1.0", draft["text"])
        buttons = tk.Frame(dialog)
        buttons.pack(fill="x", padx=12, pady=10)

        def approve():
            try:
                approve_scope_draft(self.jobs, job_number, text.get("1.0", "end"))
            except (ValueError, OSError) as exc:
                messagebox.showerror("Scope review", str(exc), parent=dialog)
                return
            dialog.destroy()
            self.start_scan(job_number, draft.get("demo_pages") or None,
                            draft.get("new_work_pages") or None)

        tk.Button(buttons, text="Approve and generate scope", command=approve).pack(side="right")
        tk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=8)

    def choose_pages(self, job_number: str):
        demo = simpledialog.askstring(
            "Demo pages", "Which page numbers are DEMOLITION drawings? (e.g. 2,3)", parent=self)
        new = simpledialog.askstring(
            "New work pages", "Which page numbers are NEW CONSTRUCTION drawings? (e.g. 4,5)", parent=self)
        try:
            demo_pages = [int(x) for x in (demo or "").replace(" ", "").split(",") if x]
            new_pages = [int(x) for x in (new or "").replace(" ", "").split(",") if x]
        except ValueError:
            messagebox.showerror("Pages", "Please enter page numbers separated by commas.")
            return
        if demo_pages or new_pages:
            self.start_scan(job_number, demo_pages or None, new_pages or None)

    def start_scan(self, job_number: str, demo_pages=None, new_pages=None):
        if job_number in self.running:
            return
        self.running.add(job_number)
        self.show_dashboard()

        def work():
            outcome = run_job_scan(self.jobs, job_number, demo_pages, new_pages)
            self.after(0, lambda: self._scan_done(job_number, outcome))

        threading.Thread(target=work, daemon=True).start()

    def _scan_done(self, job_number: str, outcome: dict):
        self.running.discard(job_number)
        self.show_dashboard()
        status = outcome.get("status")
        if status == "completed":
            if (outcome.get("ai_note") or "").startswith("AI review was skipped"):
                messagebox.showinfo("AI review", outcome["ai_note"] + "\n\nThe normal BOM was still generated.")
            self.open_review(job_number)
            return
        if status == "needs_scope_review":
            self.review_scope(job_number)
            return
        title = "BOM needs review" if status == "needs_clarification" else "BOM failed"
        messagebox.showwarning(title, f"Job {job_number}: {outcome.get('message')}")

    def open_new_job_window(self, job_number: str = "", files: dict | None = None):
        NewJobWindow(self, job_number=job_number, files=files)


class AISettingsWindow(tk.Toplevel):
    """Turn the optional AI review on or off and choose the provider and key."""

    def __init__(self, parent):
        super().__init__(parent)
        from app.services import ai_review

        self.ai = ai_review
        self.settings = ai_review.load_settings()
        self.title("AI settings")
        self.geometry("680x700")
        self.scroller = ScrollFrame(self, padx=20, pady=20)
        self.scroller.pack(fill="both", expand=True)
        self.body = self.scroller.body
        self.enabled = tk.BooleanVar(value=bool(self.settings.get("enabled")))
        tk.Checkbutton(self.body, text="Use AI to double-check the BOM when it is generated",
                       variable=self.enabled).pack(anchor="w")
        tk.Label(self.body, text="Provider:").pack(anchor="w", pady=(12, 0))
        self.labels = {cls.label: name for name, cls in ai_review.PROVIDERS.items()}
        self.provider = ttk.Combobox(self.body, values=list(self.labels), state="readonly", width=44)
        current = next((l for l, n in self.labels.items() if n == self.settings.get("provider")),
                       next(iter(self.labels)))
        self.provider.set(current)
        self.provider.pack(anchor="w")
        self.active_provider = self.labels[current]
        tk.Label(self.body, text="API key:").pack(anchor="w", pady=(12, 0))
        self.key = tk.Entry(self.body, width=48, show="*")
        self.key.insert(0, self.settings.get("api_key", ""))
        self.key.pack(anchor="w")
        tk.Label(self.body, text="Vision-capable model (leave blank for the provider default):"
                 ).pack(anchor="w", pady=(12, 0))
        self.model = tk.Entry(self.body, width=48)
        self.model.insert(0, (self.settings.get("models") or {}).get(self.settings.get("provider"), ""))
        self.model.pack(anchor="w")
        tk.Label(self.body, text="Custom OpenAI-compatible HTTPS base URL (include /v1):").pack(anchor="w", pady=(12, 0))
        self.base_url = tk.Entry(self.body, width=48)
        self.base_url.insert(0, (self.settings.get("base_urls") or {}).get(self.active_provider, ""))
        self.base_url.pack(anchor="w")
        self.guidance = tk.Label(self.body, justify="left", anchor="w", wraplength=600, fg="#333")
        self.guidance.pack(fill="x", pady=(12, 0))
        links = tk.Frame(self.body)
        links.pack(anchor="w")
        self.key_link = tk.Button(links, text="Open API key page", command=lambda: self._open_help_link(1))
        self.key_link.pack(side="left", padx=(0, 6))
        self.models_link = tk.Button(links, text="Open model catalog", command=lambda: self._open_help_link(2))
        self.models_link.pack(side="left")
        self._set_endpoint_state()
        self.provider.bind("<<ComboboxSelected>>", self._change_provider)
        tk.Label(self.body, justify="left", fg="#555", text=(
            "Each provider needs its own API key and vision-capable model.\n"
            "ChatGPT uses an OpenAI API key; ChatGPT subscriptions do not include API access.\n"
            "Grok, Groq, Mistral, OpenRouter and Together require a model ID.\n"
            "When enabled, drawing pages and scope are sent to the selected provider.\n"
            "AI-transcribed BOM rows are provisional and must be checked.")
        ).pack(anchor="w", pady=(10, 0))
        row = tk.Frame(self.body)
        row.pack(anchor="e", pady=(14, 0))
        tk.Button(row, text="Help", command=lambda: HelpWindow(self, "AI setup"), width=10).pack(side="left")
        tk.Button(row, text="Cancel", command=self.destroy, width=10).pack(side="right", padx=(6, 0))
        tk.Button(row, text="Save", command=self.save, width=10, bg="#2196F3", fg="white").pack(side="right")

    def _remember_fields(self):
        for field, value in (("api_keys", self.key.get()), ("models", self.model.get()),
                             ("base_urls", self.base_url.get())):
            values = dict(self.settings.get(field) or {})
            if value.strip():
                values[self.active_provider] = value.strip()
            else:
                values.pop(self.active_provider, None)
            self.settings[field] = values

    def _change_provider(self, _event=None):
        self._remember_fields()
        self.active_provider = self.labels[self.provider.get()]
        self.base_url.configure(state="normal")
        for widget, field in ((self.key, "api_keys"), (self.model, "models"), (self.base_url, "base_urls")):
            widget.delete(0, "end")
            widget.insert(0, (self.settings.get(field) or {}).get(self.active_provider, ""))
        self._set_endpoint_state()

    def _set_endpoint_state(self):
        self.base_url.configure(state="normal" if self.active_provider == "openai_compatible" else "disabled")
        self.guidance.configure(text=provider_guidance(self.active_provider, self.ai.PROVIDERS[self.active_provider]))
        for button, url in zip((self.key_link, self.models_link), PROVIDER_HELP[self.active_provider][1:]):
            button.configure(state="normal" if url else "disabled")

    def _open_help_link(self, index: int):
        url = PROVIDER_HELP[self.active_provider][index]
        if url and not webbrowser.open(url):
            messagebox.showwarning("Help", f"Could not open your browser. Visit:\n{url}", parent=self)

    def save(self):
        key = self.key.get().strip()
        if self.enabled.get() and not key:
            messagebox.showwarning("AI settings", "Enter an API key to turn AI review on.", parent=self)
            return
        if self.enabled.get() and self.active_provider == "openai_compatible" and (
                not self.model.get().strip() or not self.base_url.get().strip()):
            messagebox.showwarning("AI settings", "Enter a model and HTTPS base URL for this provider.", parent=self)
            return
        if self.enabled.get() and issubclass(self.ai.PROVIDERS[self.active_provider],
                                             self.ai.VisionEndpointProvider) and not self.model.get().strip():
            messagebox.showwarning("AI settings", "Enter a vision-capable model ID for this provider.", parent=self)
            return
        self._remember_fields()
        self.settings.update(enabled=self.enabled.get(), api_key=key, provider=self.active_provider)
        self.ai.save_settings(self.settings)
        self.destroy()


class HelpWindow(tk.Toplevel):
    def __init__(self, parent, selected: str = "Getting started"):
        super().__init__(parent)
        self.title("Help")
        self.geometry("720x580")
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=12)
        for title, text in HELP_SECTIONS.items():
            frame = ScrollFrame(self.tabs, padx=15, pady=15)
            self.tabs.add(frame, text=title)
            tk.Label(frame.body, text=text, justify="left", anchor="nw", wraplength=620).pack(fill="both", expand=True)
            if title == selected:
                self.tabs.select(frame)


class NewJobWindow(tk.Toplevel):
    def __init__(self, parent, job_number: str = "", files: dict | None = None):
        super().__init__(parent)
        self.parent = parent
        self.title("New Job")
        self.geometry("450x400")
        self.scroller = ScrollFrame(self, padx=20, pady=20)
        self.scroller.pack(fill="both", expand=True)
        self.body = self.scroller.body
        self.files: dict[str, str] = dict(files or {})

        tk.Label(self.body, text="Job Number:").pack(anchor="w")
        self.job_number_entry = tk.Entry(self.body, width=40)
        self.job_number_entry.pack(pady=5)
        self.job_number_entry.insert(0, job_number)
        self.job_number_entry.focus_set()

        self.pid_label = self._drop_area("P&ID File", "pid")
        self.scope_label = self._drop_area("Scope File (optional)", "scope")

        tk.Button(self.body, text="Create Job", command=self.submit, width=20,
                  bg="#4CAF50", fg="white").pack(pady=10)

    def _drop_area(self, title: str, key: str) -> tk.Label:
        tk.Label(self.body, text=f"{title}:").pack(anchor="w", pady=(10, 0))
        current = self.files.get(key)
        area = tk.Label(self.body, text=current or f"Drag & drop {title} here", relief="groove",
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
        if "pid" not in self.files:
            messagebox.showerror("Error", "Provide the P&ID file.")
            return
        try:
            data = self.parent.jobs.add_job_files(
                job_number, self.files["pid"], self.files.get("scope")
            )
        except (OSError, ValueError) as exc:
            messagebox.showerror("Error", f"Could not create job: {exc}")
            return
        messagebox.showinfo(
            "Job Created",
            f"Job {job_number} created.\n\nJob file: {data.get('job_file')}\n"
            f"P&ID: {data.get('pid_file')}\nScope: {data.get('scope_file') or 'none (taken from the P&ID)'}\n\n"
            "Click the job on the dashboard to generate its BOM.",
        )
        self.parent.show_dashboard()
        self.destroy()


def main():
    JobManagerApp().mainloop()


if __name__ == "__main__":
    main()
