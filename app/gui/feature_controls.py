"""Desktop scan progress and configurable Ollama fallback integration."""
from __future__ import annotations

from contextvars import ContextVar
import re
import threading

_PROGRESS: ContextVar = ContextVar("scan_progress_callback", default=None)
_INSTALLED = False


def _fallback_enabled(ai_review) -> bool:
    return bool(ai_review.load_settings().get("ollama_fallback_enabled", True))


def _report(message: str, completed: int, total: int = 4) -> None:
    callback = _PROGRESS.get()
    if callback:
        try:
            callback(message, completed, total)
        except Exception:
            # Progress reporting must never fail a scan.
            pass


def install() -> None:
    """Install the small compatibility hooks used by both supported app entrypoints."""
    global _INSTALLED
    if _INSTALLED:
        return

    from app.services import ai_review, job_scan, ollama_runtime, scope_bom, scope_work

    original_provider = ai_review.OllamaProvider

    class ConfigurableOllamaProvider(original_provider):
        def generate(self, prompt: str, images: list[bytes]) -> str:
            if not _fallback_enabled(ai_review):
                raise ai_review.AIError(
                    "Local Ollama fallback is disabled in AI settings. Configure or restore the primary AI provider."
                )
            match = re.search(r"image is page (\d+) of the original (\d+)-page", prompt)
            if match:
                _report(f"Ollama fallback: reviewing drawing page {match.group(1)} of {match.group(2)}", 3)
            else:
                _report("Ollama fallback: reviewing drawing", 3)
            return super().generate(prompt, images)

    ai_review.OllamaProvider = ConfigurableOllamaProvider

    original_configured = ai_review.is_configured

    def is_configured() -> bool:
        try:
            ai_review.get_provider()
            return True
        except ai_review.AIError:
            if not _fallback_enabled(ai_review):
                return False
            return bool(ollama_runtime.ollama_executable()) or original_configured()

    ai_review.is_configured = is_configured

    original_prepare = ollama_runtime.prepare_local_fallback

    def prepare_local_fallback() -> None:
        if _fallback_enabled(ai_review):
            original_prepare()

    ollama_runtime.prepare_local_fallback = prepare_local_fallback

    original_build = scope_bom.build_scoped_bom

    def build_scoped_bom(*args, **kwargs):
        _report("Reading drawing and building the BOM", 1)
        result = original_build(*args, **kwargs)
        _report("Drawing analysis and BOM build complete", 2)
        return result

    scope_bom.build_scoped_bom = build_scoped_bom

    original_review = ai_review.review_with_ai

    def review_with_ai(*args, **kwargs):
        _report("Reviewing the drawing with AI", 2)
        result = original_review(*args, **kwargs)
        _report("AI review complete", 3)
        return result

    ai_review.review_with_ai = review_with_ai

    original_transcribe = ai_review.transcribe_bom_with_ai

    def transcribe_bom_with_ai(pdf_path, page_number, *args, **kwargs):
        _report(f"Transcribing printed BOM on page {page_number}", 2)
        return original_transcribe(pdf_path, page_number, *args, **kwargs)

    ai_review.transcribe_bom_with_ai = transcribe_bom_with_ai

    original_draft = scope_work.create_scope_draft

    def create_scope_draft(*args, **kwargs):
        _report("Preparing a scope draft for your review", 3)
        result = original_draft(*args, **kwargs)
        _report("Scope draft ready for review", 4)
        return result

    scope_work.create_scope_draft = create_scope_draft

    original_scan = job_scan.run_job_scan

    def run_job_scan_with_progress(jm, job_number, demo_pages=None, new_work_pages=None,
                                   progress_callback=None):
        token = _PROGRESS.set(progress_callback)
        _report("Preparing job scan", 0)
        try:
            outcome = original_scan(jm, job_number, demo_pages, new_work_pages)
            _report("Scan finished", 4)
            return outcome
        finally:
            _PROGRESS.reset(token)

    job_scan.run_job_scan = run_job_scan_with_progress
    _INSTALLED = True


def _install_gui_hooks(gui) -> None:
    """Attach progress display and the fallback checkbox without replacing existing screens."""
    original_row = gui.JobManagerApp._job_row

    def job_row(self, parent, meta):
        original_row(self, parent, meta)
        number = meta.get("job_number") or meta.get("job_safe_name") or "?"
        progress = getattr(self, "_scan_progress", {}).get(number)
        if number not in self.running or not progress:
            return

        def visit(widget):
            for child in widget.winfo_children():
                if isinstance(child, gui.ttk.Progressbar):
                    child.stop()
                    child.configure(mode="determinate", maximum=progress[2], value=progress[1])
                elif isinstance(child, gui.tk.Label) and child.cget("text") == "Generating BOM...":
                    child.configure(text=progress[0])
                visit(child)
        visit(parent)

    gui.JobManagerApp._job_row = job_row

    def render_progress(self, job_number, message, completed, total):
        self._scan_progress[job_number] = (message, completed, total)
        self.show_dashboard()

    gui.JobManagerApp._render_scan_progress = render_progress

    def start_scan(self, job_number, demo_pages=None, new_pages=None):
        if job_number in self.running:
            return
        self._scan_progress = getattr(self, "_scan_progress", {})
        self._scan_progress[job_number] = ("Preparing job scan", 0, 4)
        self.running.add(job_number)
        self.show_dashboard()

        def work():
            def report(message, completed, total):
                try:
                    self.after(0, lambda m=message, c=completed, t=total:
                               self._render_scan_progress(job_number, m, c, t))
                except Exception:
                    pass
            outcome = gui.run_job_scan(self.jobs, job_number, demo_pages, new_pages,
                                       progress_callback=report)
            try:
                self.after(0, lambda: self._scan_done(job_number, outcome))
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    gui.JobManagerApp.start_scan = start_scan
    original_done = gui.JobManagerApp._scan_done

    def scan_done(self, job_number, outcome):
        getattr(self, "_scan_progress", {}).pop(job_number, None)
        return original_done(self, job_number, outcome)

    gui.JobManagerApp._scan_done = scan_done

    original_settings = gui.AISettingsWindow

    class AISettingsWindowWithFallback(original_settings):
        def __init__(self, parent):
            super().__init__(parent)
            self.ollama_fallback_enabled = gui.tk.BooleanVar(
                value=bool(self.settings.get("ollama_fallback_enabled", True)))
            gui.ttk.Checkbutton(
                self.body,
                text="Use local Ollama if the selected AI provider is unavailable or fails",
                variable=self.ollama_fallback_enabled,
            ).pack(anchor="w", pady=(10, 0))
            gui.tk.Label(
                self.body,
                text="Turn this off to prevent local Ollama from receiving scan data. AI review will fail if the selected provider cannot be used.",
                justify="left", wraplength=600, fg="#555",
            ).pack(anchor="w")

        def save(self):
            self.settings["ollama_fallback_enabled"] = bool(self.ollama_fallback_enabled.get())
            enabled = self.settings["ollama_fallback_enabled"]
            super().save()
            if enabled:
                ollama_runtime.prepare_local_fallback()
            else:
                ollama_runtime.stop_owned_server()

    gui.AISettingsWindow = AISettingsWindowWithFallback


def main() -> None:
    install()
    from app.gui import job_manager_gui

    _install_gui_hooks(job_manager_gui)
    job_manager_gui.main()
