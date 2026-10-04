"""Tkinter Job Manager: login, dashboard and new-job screens.

Launch with: python -m app.gui
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from tkinterdnd2 import DND_FILES, TkinterDnD

PLACEHOLDER_JOBS = [
    "Job #1001 - Refinery Upgrade",
    "Job #1002 - Pipeline Inspection",
    "Job #1003 - Maintenance",
]


def parse_dropped_files(tk_root, data: str) -> list[str]:
    """Split a tkdnd drop payload (handles paths with spaces) into paths."""
    return list(tk_root.tk.splitlist(data))


class JobManagerApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("Job Manager App")
        self.geometry("500x400")
        self.configure(padx=20, pady=20)
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
        for job in PLACEHOLDER_JOBS:
            link = tk.Label(jobs_frame, text=job, fg="blue", cursor="hand2",
                            font=("Arial", 10, "underline"))
            link.pack(anchor="w", pady=2)
            link.bind("<Button-1>", lambda _e, j=job: messagebox.showinfo("Job", f"Opening {j}"))

    def open_new_job_window(self):
        NewJobWindow(self)


class NewJobWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
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
        messagebox.showinfo("Job Created", f"Job {job_number} created (placeholder).")
        self.destroy()


def main():
    JobManagerApp().mainloop()


if __name__ == "__main__":
    main()
