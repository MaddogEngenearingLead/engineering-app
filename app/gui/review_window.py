"""Review window: check, correct and annotate a generated BOM, then re-export it."""
from __future__ import annotations

import base64
import io
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from app.services.job_scan import load_review, save_review
from app.services.review_questions import (apply_answer, build_questions, ensure_uids, undo_answer)


def render_location(pdf_path: str, page: int, x: float, y: float, half: int = 260):
    """PNG bytes of the drawing around (x, y) with the spot circled."""
    import pdfplumber
    from PIL import ImageDraw

    with pdfplumber.open(pdf_path) as pdf:
        pg = pdf.pages[page - 1]
        scale = 1.5
        # render the whole page, then crop: cropping first misplaces rotated pages
        img = pg.to_image(resolution=72 * scale).original.convert("RGB")
        sx, sy = img.width / float(pg.width), img.height / float(pg.height)
        cx, cy = x * sx, y * sy
        draw = ImageDraw.Draw(img)
        r = 55
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(255, 0, 255), width=5)
        box = (max(0, cx - half * scale), max(0, cy - half * 0.7 * scale),
               min(img.width, cx + half * scale), min(img.height, cy + half * 0.7 * scale))
        buf = io.BytesIO()
        img.crop(tuple(int(v) for v in box)).save(buf, format="PNG")
        return buf.getvalue()


def render_page(pdf_path: str, page: int, width: int = 1100) -> bytes:
    """PNG bytes of a whole drawing page, scaled to fit the screen."""
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        pg = pdf.pages[page - 1]
        img = pg.to_image(resolution=72 * width / float(pg.width)).original.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


class LocationViewer(tk.Toplevel):
    """Drawing viewer: Previous/Next through an item's locations, zoom in/out."""
    VIEW_W, VIEW_H = 900, 600
    RENDER_SCALE = 3.0  # pixels per PDF point; zooming crops this rendering

    def __init__(self, parent, pdf_path: str, title: str, locs: list[dict], page: int | None = None):
        super().__init__(parent)
        self.pdf_path, self.locs, self.whole_page = pdf_path, locs, page
        self.index, self.zoom = 0, 1.0
        self._pages: dict[int, object] = {}
        self.title(title)
        bar = tk.Frame(self)
        bar.pack(fill="x", padx=6, pady=4)
        self.prev_btn = tk.Button(bar, text="< Previous", command=lambda: self.step(-1))
        self.next_btn = tk.Button(bar, text="Next >", command=lambda: self.step(1))
        for b in (self.prev_btn, self.next_btn):
            b.pack(side="left", padx=2)
        self.counter = tk.Label(bar, font=("Arial", 10, "bold"))
        self.counter.pack(side="left", padx=10)
        tk.Button(bar, text="Zoom +", command=lambda: self.set_zoom(self.zoom * 1.5)).pack(side="right", padx=2)
        tk.Button(bar, text="Zoom -", command=lambda: self.set_zoom(self.zoom / 1.5)).pack(side="right", padx=2)
        self.label = tk.Label(self)
        self.label.pack()
        tk.Label(self, fg="gray", text="Left/Right arrows = previous/next   + / - or mouse wheel = zoom"
                 ).pack(pady=(0, 4))
        self.bind("<Left>", lambda _e: self.step(-1))
        self.bind("<Right>", lambda _e: self.step(1))
        for k in ("<plus>", "<equal>", "<KP_Add>"):
            self.bind(k, lambda _e: self.set_zoom(self.zoom * 1.5))
        for k in ("<minus>", "<KP_Subtract>"):
            self.bind(k, lambda _e: self.set_zoom(self.zoom / 1.5))
        self.bind("<MouseWheel>", lambda e: self.set_zoom(self.zoom * (1.25 if e.delta > 0 else 0.8)))
        self.bind("<Button-4>", lambda _e: self.set_zoom(self.zoom * 1.25))
        self.bind("<Button-5>", lambda _e: self.set_zoom(self.zoom * 0.8))
        self.focus_set()
        self.show()

    def _page_image(self, page: int):
        if page not in self._pages:
            import pdfplumber
            with pdfplumber.open(self.pdf_path) as pdf:
                pg = pdf.pages[page - 1]
                self._pages[page] = (pg.to_image(resolution=72 * self.RENDER_SCALE).original.convert("RGB"),
                                     float(pg.width), float(pg.height))
        return self._pages[page]

    def step(self, delta: int):
        if len(self.locs) > 1:
            self.index = (self.index + delta) % len(self.locs)
            self.show()

    def set_zoom(self, value: float):
        self.zoom = min(8.0, max(0.15, value))
        self.show()

    def show(self):
        from PIL import ImageDraw

        loc = self.locs[self.index] if self.locs else {"page": self.whole_page}
        img, pw, ph = self._page_image(int(loc["page"]))
        k = img.width / pw
        # zoom 1.0 shows about 520 x 350 pt around the item; whole pages start fitted to the window
        view_w_pt = (520 if self.locs else pw) / self.zoom
        view_h_pt = view_w_pt * self.VIEW_H / self.VIEW_W
        if self.locs:
            cx, cy = loc["x"] * k, loc["y"] * k
            draw = ImageDraw.Draw(img := img.copy())
            r = 55 / self.zoom ** 0.3 * self.RENDER_SCALE / 1.5
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(255, 0, 255), width=int(5 * self.RENDER_SCALE / 1.5))
        else:
            cx, cy = img.width / 2, img.height / 2
        w, h = view_w_pt * k, view_h_pt * k
        left = min(max(0, cx - w / 2), max(0, img.width - w))
        top = min(max(0, cy - h / 2), max(0, img.height - h))
        crop = img.crop((int(left), int(top), int(min(img.width, left + w)), int(min(img.height, top + h))))
        crop = crop.resize((self.VIEW_W, int(self.VIEW_W * crop.height / max(1, crop.width))))
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        self.photo = tk.PhotoImage(data=base64.b64encode(buf.getvalue()))
        self.label.config(image=self.photo)
        n = len(self.locs)
        grid = loc.get("grid", "")
        self.counter.config(text=(f"{self.index + 1} of {n}  -  page {loc['page']} {grid}" if n
                                  else f"Page {loc['page']} (whole page)") + f"   zoom {self.zoom:.1f}x")
        state = "normal" if n > 1 else "disabled"
        self.prev_btn.config(state=state)
        self.next_btn.config(state=state)


class QuestionDialog(tk.Toplevel):
    """Shows one question: what is asked, why, where, and the answer controls."""

    def __init__(self, parent, q: dict, previous: dict | None, show_cb):
        super().__init__(parent)
        self.q, self.result = q, None
        self.title("Question")
        self.configure(padx=14, pady=12)
        prev_in = (previous or {}).get("input") or {}
        tk.Label(self, text=q["title"], font=("Arial", 12, "bold"), wraplength=620, justify="left"
                 ).pack(anchor="w")
        tk.Label(self, text=q["question"], wraplength=620, justify="left").pack(anchor="w", pady=(8, 4))
        why = tk.LabelFrame(self, text="Why am I being asked?", padx=6, pady=4)
        why.pack(fill="x", pady=6)
        tk.Label(why, text=q["why"], wraplength=600, justify="left", fg="#444").pack(anchor="w")
        if q.get("locations"):
            tk.Button(self, text=f"Show on drawing ({len(q['locations'])} location"
                                 f"{'s' if len(q['locations']) != 1 else ''})", relief="groove",
                      command=lambda: show_cb(q)).pack(anchor="w", pady=4)

        self.choice = tk.StringVar(value=prev_in.get("choice") or "")
        for value, label in q.get("choices", []):
            tk.Radiobutton(self, text=label, variable=self.choice, value=value, justify="left",
                           wraplength=600).pack(anchor="w")
        self.checks = {}
        if q["kind"] == "checklist":
            box = tk.Frame(self)
            box.pack(fill="x")
            for it in q["items"]:
                var = tk.BooleanVar(value=it["tag"] in (prev_in.get("checks") or []))
                self.checks[it["tag"]] = var
                tk.Checkbutton(box, variable=var, anchor="w", justify="left",
                               text=f"{it['tag']} - {it['description']} (x{it['quantity']}, {it['location']})"
                               ).pack(anchor="w")
        self.fields = {}
        prev_fields = prev_in.get("fields") or {}
        for fld in q.get("fields", []):
            row = tk.Frame(self)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=fld["label"], width=48, anchor="w", wraplength=330, justify="left").pack(side="left")
            var = tk.StringVar(value=prev_fields.get(fld["key"], fld["default"]))
            tk.Entry(row, textvariable=var, width=30).pack(side="left")
            self.fields[fld["key"]] = var
        tk.Label(self, text="Comment (optional, saved on the BOM):").pack(anchor="w", pady=(8, 0))
        self.comment = tk.StringVar(value=prev_in.get("comment", ""))
        tk.Entry(self, textvariable=self.comment, width=80).pack(anchor="w")
        row = tk.Frame(self)
        row.pack(fill="x", pady=(12, 0))
        tk.Button(row, text="Cancel", command=self.destroy).pack(side="right", padx=4)
        tk.Button(row, text="Apply answer", bg="#4CAF50", fg="white", command=self.ok).pack(side="right")
        self.grab_set()
        self.transient(parent)

    def ok(self):
        if self.q.get("choices") and not self.choice.get():
            messagebox.showinfo("Answer", "Please pick one of the options.", parent=self)
            return
        self.result = {"choice": self.choice.get() or None,
                       "checks": [t for t, v in self.checks.items() if v.get()],
                       "fields": {k: v.get() for k, v in self.fields.items()},
                       "comment": self.comment.get()}
        self.destroy()


class ItemDialog(simpledialog.Dialog):
    def __init__(self, parent, title: str, item: dict):
        self.item = item
        self.result = None
        super().__init__(parent, title)

    def body(self, master):
        self.vars = {}
        for r, (key, label) in enumerate((("tag_id", "Tag"), ("description", "Description"),
                                          ("quantity", "Quantity"), ("unit", "Unit"),
                                          ("location", "Location"), ("note", "Note"))):
            tk.Label(master, text=label).grid(row=r, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=str(self.item.get(key, "") or ""))
            tk.Entry(master, textvariable=var, width=50).grid(row=r, column=1, pady=2)
            self.vars[key] = var
        return None

    def validate(self):
        try:
            float(self.vars["quantity"].get())
        except ValueError:
            messagebox.showerror("Quantity", "Quantity must be a number.", parent=self)
            return False
        return True

    def apply(self):
        values = {k: v.get().strip() for k, v in self.vars.items()}
        q = float(values["quantity"])
        values["quantity"] = int(q) if q == int(q) else q
        self.result = values


class ReviewWindow(tk.Toplevel):
    def __init__(self, parent, jm, job_number: str, on_saved=None):
        super().__init__(parent)
        self.jm, self.job_number, self.on_saved = jm, job_number, on_saved
        self.title(f"Review BOM - Job #{job_number}")
        self.geometry("1000x760")
        review = load_review(jm, job_number)
        if not review:
            messagebox.showinfo("Review", "Generate the BOM first.", parent=parent)
            self.destroy()
            return
        self.pid_file = review["pid_file"]
        self.result = review["result"]
        self.materials = [dict(m) for m in review["materials"]]
        self.clarifications: list[str] = list(review.get("clarifications", []))
        self.answers: dict = dict(review.get("answers", {}))
        ensure_uids(self.materials)
        self.questions = build_questions(self.result.get("flags", []), self.materials)
        
        self._build()
        self._fill()

    def _build(self):
        s = self.result.get("summary") or {}
        if s:
            tk.Label(self, text="  |  ".join(f"{k.replace('_', ' ')}: {v}" for k, v in s.items()
                                              if isinstance(v, (int, str))),
                     fg="gray", wraplength=960, justify="left").pack(anchor="w", padx=8, pady=(8, 0))

        cols = ("n", "tag", "desc", "qty", "loc", "basis")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=10, selectmode="browse")
        for c, label, w in (("n", "#", 35), ("tag", "Tag", 90), ("desc", "Description", 250),
                            ("qty", "Qty", 45), ("loc", "Location (page / grid)", 220),
                            ("basis", "Why it is on the BOM", 330)):
            self.tree.heading(c, text=label)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=8, pady=6)
        self.tree.bind("<Double-1>", lambda _e: self.edit_item())

        bar = tk.Frame(self)
        bar.pack(fill="x", padx=8)
        for text, cmd in (("Show on drawing", self.show_location), ("Edit", self.edit_item),
                          ("Remove", self.remove_item), ("Add item", self.add_item)):
            tk.Button(bar, text=text, command=cmd, relief="groove").pack(side="left", padx=(0, 6))

        self.q_title = tk.Label(self, font=("Arial", 10, "bold"))
        self.q_title.pack(anchor="w", padx=8, pady=(10, 2))
        self.flags = tk.Listbox(self, height=7)
        self.flags.pack(fill="x", padx=8)
        self.flags.bind("<Double-1>", lambda _e: self.answer_flag())
        tk.Button(self, text="Answer selected question", command=self.answer_flag, relief="groove"
                  ).pack(anchor="w", padx=8, pady=3)
        self._fill_questions()

        tk.Label(self, text="Clarifications (saved on the BOM):", font=("Arial", 10, "bold")
                 ).pack(anchor="w", padx=8, pady=(10, 2))
        self.notes = tk.Listbox(self, height=4)
        self.notes.pack(fill="x", padx=8)
        for n in self.clarifications:
            self.notes.insert("end", n)
        bar2 = tk.Frame(self)
        bar2.pack(fill="x", padx=8, pady=8)
        tk.Button(bar2, text="Add clarification note", command=self.add_note, relief="groove").pack(side="left")
        tk.Button(bar2, text="Save and re-export BOM", command=self.save, bg="#4CAF50", fg="white"
                  ).pack(side="right")

    def _fill(self):
        self.tree.delete(*self.tree.get_children())
        for i, m in enumerate(self.materials):
            desc = m.get("description", "")
            if m.get("note"):
                desc += f"  [{m['note']}]"
            self.tree.insert("", "end", iid=str(i), values=(
                i + 1, m.get("tag_id", ""), desc, m.get("quantity", ""),
                m.get("location") or "-", m.get("basis", "")))

    def _selected(self) -> int | None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Review", "Select an item first.", parent=self)
            return None
        return int(sel[0])

    def edit_item(self):
        i = self._selected()
        if i is None:
            return
        dlg = ItemDialog(self, "Edit item", self.materials[i])
        if dlg.result:
            self.materials[i].update(dlg.result)
            self._fill()

    def remove_item(self):
        i = self._selected()
        if i is not None and messagebox.askyesno("Remove", "Remove this item from the BOM?", parent=self):
            del self.materials[i]
            self._fill()

    def add_item(self):
        dlg = ItemDialog(self, "Add item", {"quantity": 1, "unit": "EA"})
        if dlg.result:
            dlg.result.update(type="added_by_user", origin="user", basis="added during review",
                              confidence=1.0)
            self.materials.append(dlg.result)
            self._fill()

    def add_note(self, text: str | None = None):
        text = text or simpledialog.askstring("Clarification", "Note to add to the BOM:", parent=self)
        if text and text.strip():
            self.clarifications.append(text.strip())
            self.notes.insert("end", text.strip())

    def _fill_questions(self):
        sel = self.flags.curselection()
        self.flags.delete(0, "end")
        for q in self.questions:
            done = q["id"] in self.answers
            self.flags.insert("end", f"{'[answered]' if done else '[OPEN]    '}  {q['title']}")
            self.flags.itemconfig("end", fg="#0a7d2c" if done else ("#b36b00" if q["severity"] != "info" else "#555"))
        open_n = sum(1 for q in self.questions if q["id"] not in self.answers)
        self.q_title.config(text=f"Questions the scan couldn't settle ({open_n} open of {len(self.questions)}) "
                                 "- double-click one to read it and answer:")
        if sel:
            self.flags.selection_set(sel[0])

    def _show_question(self, q: dict):
        locs = q.get("locations") or []
        try:
            LocationViewer(self, self.pid_file, q["title"], locs, None)
        except Exception as exc:
            messagebox.showerror("Location", f"Could not draw the P&ID: {exc}", parent=self)

    def answer_flag(self):
        sel = self.flags.curselection()
        if not sel:
            messagebox.showinfo("Question", "Select a question first.", parent=self)
            return
        q = self.questions[sel[0]]
        previous = self.answers.get(q["id"])
        dlg = QuestionDialog(self, q, previous, self._show_question)
        self.wait_window(dlg)
        if not dlg.result:
            return
        if previous:
            undo_answer(self.materials, previous)
        self.answers[q["id"]] = apply_answer(self.materials, q, dlg.result)
        self._fill()
        self._fill_questions()

    def show_location(self):
        i = self._selected()
        if i is None:
            return
        m = self.materials[i]
        locs = m.get("locations") or []
        if not locs and not m.get("page"):
            messagebox.showinfo("Location", "No drawing location is known for this item.", parent=self)
            return
        name = m.get("tag_id") if m.get("tag_id") not in (None, "-") else m.get("description")
        try:
            LocationViewer(self, self.pid_file, f"{name} - drawing", locs, int(m["page"]) if m.get("page") else None)
        except Exception as exc:
            messagebox.showerror("Location", f"Could not draw the P&ID: {exc}", parent=self)

    def save(self):
        try:
            open_n = sum(1 for q in self.questions if q["id"] not in self.answers)
            if open_n and not messagebox.askyesno(
                    "Open questions", f"{open_n} question(s) are still unanswered and will be listed as "
                    "'needs review' on the BOM. Save anyway?", parent=self):
                return
            save_review(self.jm, self.job_number, self.materials, self.clarifications, self.answers)
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc), parent=self)
            return
        messagebox.showinfo("Saved", "BOM re-exported with your changes.", parent=self)
        if self.on_saved:
            self.on_saved()
        self.destroy()
