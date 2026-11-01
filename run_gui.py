"""Entry point for the Job Manager desktop GUI (also used for the PyInstaller build)."""
import sys


def selftest() -> int:
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
    d = Path(tempfile.mkdtemp())
    c = canvas.Canvas(str(d / "pid.pdf"))
    c.drawString(72, 750, "DEMOLITION P&ID"); c.drawString(72, 720, "TK-1 TANK"); c.showPage()
    c.drawString(72, 750, "NEW WORK P&ID"); c.drawString(72, 720, "TK-1 TANK"); c.drawString(72, 700, "MOV-001 VALVE")
    c.save()
    (d / "scope.txt").write_text("Install tank TK-1 and valve MOV-001.")
    jm = JobManager(str(d / "uploads"))
    jm.create_job("T-1")
    jm.add_job_files("T-1", str(d / "pid.pdf"), str(d / "scope.txt"))
    out = run_job_scan(jm, "T-1")
    print("SELFTEST", out["status"], out.get("message"))
    return 0 if out["status"] == "completed" else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    from app.gui.job_manager_gui import main

    main()
