"""Vertical scrolling for windows whose content can exceed the window size."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ScrollFrame(ttk.Frame):
    """A frame whose `body` child scrolls (scrollbar + mouse wheel) when too tall.

    Build widgets with `scroll_frame.body` as the parent. The scrollbar is only
    shown when the content is taller than the window.
    """

    def __init__(self, parent, padx: int = 0, pady: int = 0):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(self.canvas, padx=padx, pady=pady)
        self._window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._on_body_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_all(seq, self._on_wheel, add="+")

    def fit_to_content(self, max_height: int | None = None):
        """Size the window to its content, capped to the screen so the rest scrolls."""
        top = self.winfo_toplevel()
        top.update_idletasks()
        cap = max_height or int(top.winfo_screenheight() * 0.8)
        self.canvas.configure(width=self.body.winfo_reqwidth(),
                              height=min(self.body.winfo_reqheight(), cap))

    def _needs_scroll(self) -> bool:
        return self.body.winfo_reqheight() > self.canvas.winfo_height()

    def _on_body_configure(self, _event=None):
        self.canvas.configure(scrollregion=(0, 0, self.body.winfo_reqwidth(), self.body.winfo_reqheight()))
        self._update_bar()

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self._window, width=event.width)
        self._update_bar()

    def _update_bar(self):
        if self._needs_scroll():
            if not self.vbar.winfo_ismapped():
                self.vbar.pack(side="right", fill="y", before=self.canvas)
        else:
            self.vbar.pack_forget()
            self.canvas.yview_moveto(0)

    def _on_scroll(self, first, last):
        self.vbar.set(first, last)

    def _on_wheel(self, event):
        try:
            if not self.winfo_exists() or not self._needs_scroll():
                return
            # Only react to events from widgets inside this frame's own window.
            if str(event.widget).startswith(str(self.winfo_toplevel())) is False:
                return
            if event.widget.winfo_toplevel() is not self.winfo_toplevel():
                return
        except (tk.TclError, KeyError, AttributeError):
            return
        # Let list/tree widgets scroll themselves.
        if isinstance(event.widget, (tk.Listbox, ttk.Treeview, tk.Text)):
            return
        if getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        else:
            step = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(step, "units")
