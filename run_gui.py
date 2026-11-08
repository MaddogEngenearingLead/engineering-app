"""Entry point for the Job Manager desktop GUI (also used for the PyInstaller build)."""
import sys
import os


def selftest(require_bundled_ocr: bool = False, require_bundled_ollama: bool = False) -> int:
    """Import everything the app needs and run a real PDF scan; used to verify packaged builds."""
    import tempfile
    from pathlib import Path

    import certifi
    import httpx  # noqa: F401
    import tkinter  # noqa: F401
    import tkinterdnd2  # noqa: F401
    from reportlab.pdfgen import canvas

    from app.gui import job_manager_gui  # noqa: F401
    from app.job_manager import JobManager
    from app.services.job_scan import run_job_scan

    assert Path(certifi.where()).is_file(), "CA bundle missing"
    bundle = Path(getattr(sys, "_MEIPASS", "")) / "tesseract"
    ollama_runtime = Path(getattr(sys, "_MEIPASS", "")) / "ollama-runtime"
    if require_bundled_ocr:
        assert getattr(sys, "frozen", False) and bundle.is_dir(), "bundled OCR missing"
    if require_bundled_ollama:
        executable = "ollama.exe" if sys.platform.startswith("win") else "ollama"
        bundled_executable = ollama_runtime / executable
        assert getattr(sys, "frozen", False) and bundled_executable.is_file(), \
            "bundled Ollama runtime missing"
        assert sys.platform.startswith("win") or os.access(bundled_executable, os.X_OK), \
            "bundled Ollama executable is not executable"
        import subprocess

        subprocess.run([str(bundled_executable), "--version"], check=True, timeout=30)
    if getattr(sys, "frozen", False) and bundle.is_dir():
        from PIL import Image, ImageDraw, ImageFont
        from app.services.drawing_ocr import _searchable_page, _tesseract

        binary, _ = _tesseract()
        assert binary and Path(binary).is_relative_to(bundle), "bundled OCR executable missing"

        image = Image.new("RGB", (900, 180), "white")
        ImageDraw.Draw(image).text((30, 30), "BILL OF MATERIALS", font=ImageFont.load_default(size=48), fill="black")
        text, _, _, _ = _searchable_page(image, 150)
        assert "MATERIALS" in text.upper(), "bundled OCR failed"
        print("SELFTEST bundled OCR ok")
    d = Path(tempfile.mkdtemp())
    c = canvas.Canvas(str(d / "pid.pdf"))
    c.drawString(72, 750, "DEMOLITION P&ID"); c.drawString(72, 720, "TK-1 TANK"); c.showPage()
    c.drawString(72, 750, "NEW WORK P&ID"); c.drawString(72, 720, "TK-1 TANK"); c.drawString(72, 700, "MOV-001 VALVE")
    c.save()
    (d / "scope.txt").write_text("Install tank TK-1 and valve MOV-001.")
    from app.services import ai_review

    class SelfTestProvider:
        name, model = "selftest", "selftest"

    ai_review.get_provider = lambda *_args, **_kwargs: SelfTestProvider()
    ai_review.review_with_ai = lambda *_args, **_kwargs: {
        "flags": [], "summary": "Self-test review.", "key_page": None,
        "provider": "selftest", "model": "selftest"}
    jm = JobManager(str(d / "uploads"))
    jm.create_job("T-1")
    jm.add_job_files("T-1", str(d / "pid.pdf"), str(d / "scope.txt"))
    out = run_job_scan(jm, "T-1")
    print("SELFTEST", out["status"], out.get("message"))
    from app.gui.review_window import render_location
    from app.services.job_scan import load_review, save_review

    if out["status"] == "completed":
        assert render_location(str(d / "pid.pdf"), 2, 100, 100)[:4] == b"\x89PNG", "preview failed"
        review = load_review(jm, "T-1")
        save_review(jm, "T-1", review["materials"], ["selftest note"])
        print("SELFTEST review ok")
    return 0 if out["status"] == "completed" else 1


if __name__ == "__main__":
    if ("--selftest" in sys.argv or "--selftest-require-bundled-ocr" in sys.argv
            or "--selftest-require-bundled-ollama" in sys.argv):
        sys.exit(selftest(require_bundled_ocr="--selftest-require-bundled-ocr" in sys.argv,
                          require_bundled_ollama="--selftest-require-bundled-ollama" in sys.argv))
    from app.gui.job_manager_gui import main

    main()
