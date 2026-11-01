"""Review window: check, correct and annotate a generated BOM, then re-export it."""
from __future__ import annotations

import base64
import io
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from app.services.job_scan import load_review, save_review


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
        self.geometry("1000x680")
        review = load_review(jm, job_number)
        if not review:
            messagebox.showinfo("Review", "Generate the BOM first.", parent=parent)
            self.destroy()
            return
        self.pid_file = review["pid_file"]
        self.result = review["result"]
        self.materials = [dict(m) for m in review["materials"]]
        self.clarifications: list[str] = list(review.get("clarifications", []))
        self._cycle: dict[int, int] = {}
        self._build()
        self._fill()

    def _build(self):
        s = self.result.get("summary") or {}
        if s:
            tk.Label(self, text="  |  ".join(f"{k.replace('_', ' ')}: {v}" for k, v in s.items()
                                              if isinstance(v, (int, str))),
                     fg="gray", wraplength=960, justify="left").pack(anchor="w", padx=8, pady=(8, 0))

        cols = ("n", "tag", "desc", "qty", "loc", "basis")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=14, selectmode="browse")
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

        tk.Label(self, text="Questions and flags (double-click one to answer it):",
                 font=("Arial", 10, "bold")).pack(anchor="w", padx=8, pady=(10, 2))
        self.flags = tk.Listbox(self, height=6)
        self.flags.pack(fill="x", padx=8)
        self.flag_items = [f for f in self.result.get("flags", []) if f.get("message")]
        for f in self.flag_items:
            self.flags.insert("end", f["message"][:200])
        self.flags.bind("<Double-1>", lambda _e: self.answer_flag())

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

    def answer_flag(self):
        sel = self.flags.curselection()
        if not sel:
            return
        flag = self.flag_items[sel[0]]
        answer = simpledialog.askstring("Answer", flag["message"][:300], parent=self)
        if answer:
            self.add_note(f"Q: {flag['message'][:160]} -> A: {answer.strip()}")

    def show_location(self):
        i = self._selected()
        if i is None:
            return
        locs = self.materials[i].get("locations") or []
        if not locs:
            messagebox.showinfo("Location", "This item is not drawn on the P&ID "
                                "(it comes from the scope of work), so it has no location.", parent=self)
            return
        k = self._cycle.get(i, 0) % len(locs)
        self._cycle[i] = k + 1
        loc = locs[k]
        try:
            png = render_location(self.pid_file, loc["page"], loc["x"], loc["y"])
        except Exception as exc:
            messagebox.showerror("Location", f"Could not draw the P&ID: {exc}", parent=self)
            return
        win = tk.Toplevel(self)
        win.title(f"{self.materials[i].get('tag_id') or self.materials[i].get('description')} - "
                  f"page {loc['page']} {loc.get('grid', '')}  ({k + 1} of {len(locs)})")
        win.photo = tk.PhotoImage(data=base64.b64encode(png))
        tk.Label(win, image=win.photo).pack()
        tk.Label(win, text="Click 'Show on drawing' again for the next occurrence.", fg="gray").pack()

    def save(self):
        try:
            save_review(self.jm, self.job_number, self.materials, self.clarifications)
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc), parent=self)
            return
        messagebox.showinfo("Saved", "BOM re-exported with your changes.", parent=self)
        if self.on_saved:
            self.on_saved()
        self.destroy()
