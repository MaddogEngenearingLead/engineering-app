"""Turn scan flags into plain-language questions and apply the answers to the BOM.

Each question says what is being asked, why the scan asked it, and what each answer
will do. Answering changes the BOM (adds/removes items, sets quantities) and the
question is then recorded as resolved on the exported BOM instead of staying open.
"""
from __future__ import annotations

import hashlib
import uuid

NO_CHANGE = "none"


def ensure_uids(materials: list[dict]) -> None:
    """Give each item an id derived from its content so it survives a re-scan."""
    seen: set[str] = set()
    for m in materials:
        if m.get("uid"):
            seen.add(m["uid"])
            continue
        key = "|".join(str(m.get(k, "")) for k in ("tag_id", "description", "type", "pages", "page"))
        uid, n = hashlib.md5(key.encode()).hexdigest()[:8], 0
        while uid in seen:
            n += 1
            uid = hashlib.md5(f"{key}#{n}".encode()).hexdigest()[:8]
        seen.add(uid)
        m["uid"] = uid


def _loc_text(f: dict) -> str:
    return f.get("location") or ""


def build_questions(flags: list[dict], materials: list[dict]) -> list[dict]:
    """Questions for every flag worth asking about; ids are stable (flag index + type)."""
    qs: list[dict] = []
    for i, f in enumerate(flags):
        q = _question(i, f, materials)
        if q:
            qs.append(q)
    return qs


def _question(i: int, f: dict, materials: list[dict]) -> dict | None:
    t = f.get("type")
    qid = f"{t}-" + hashlib.md5(f"{t}|{f.get('message', '')}".encode()).hexdigest()[:8]
    base = {"id": qid, "flag_type": t, "severity": f.get("severity", "review"),
            "locations": [], "message": f.get("message", "")}

    if t == "named_in_scope_but_existing":
        item = f["items"][0]
        return {**base, "kind": "choice", "locations": item["locations"], "items": f["items"],
                "title": f"{f['tag']}: in the scope, but drawn as existing",
                "question": f"The scope of work mentions {f['tag']} ({item['description']}), but on the new-work "
                            f"drawing it is grey, which means existing equipment. Is work required on it "
                            f"(so it belongs on the BOM)?",
                "why": "Grey items are treated as existing and left off the BOM. The scope names this one, so the "
                       "scan can't tell whether it is being worked on or just referenced.",
                "choices": [("add", f"Yes - add {f['tag']} to the BOM"),
                            (NO_CHANGE, "No - leave it off the BOM")]}

    if t in ("unchanged_items_excluded", "future_items_excluded"):
        future = t == "future_items_excluded"
        what = "inside blue 'future work' clouds" if future else "drawn as existing (grey)"
        return {**base, "kind": "checklist", "items": f["items"],
                "locations": [l for it in f["items"] for l in it["locations"]],
                "title": ("Future-work items left off" if future else "Existing items left off")
                         + f" ({len(f['items'])})",
                "question": f"These items are {what}, so they were left off the BOM. Tick any that are actually "
                            f"needed for this job.",
                "why": ("Items in blue clouds are treated as future work and excluded." if future else
                        "Grey items on the new-work pages are treated as existing equipment that stays as-is, and "
                        "are excluded.") + " Ticked items are added to the BOM with the quantity shown.",
                "choices": []}

    if t == "count_mismatch":
        return {**base, "kind": "choice", "codes": f["codes"], "scope_qty": f["scope_qty"],
                "title": f"{f['item']}: scope and drawing counts differ",
                "question": f"The scope asks for {f['scope_qty']} x {f['item']} but the drawing shows "
                            f"{f['drawing_qty']}. Which quantity is right?",
                "why": "The BOM quantity comes from the drawing, but the scope states a different number.",
                "choices": [("drawing", f"Use the drawing count ({f['drawing_qty']})"),
                            ("scope", f"Use the scope quantity ({f['scope_qty']})"),
                            ("other", "Use a different quantity (enter below)")],
                "fields": [{"key": "qty", "label": "Quantity (only for 'different quantity')", "default": ""}]}

    if t == "markup_note":
        return {**base, "kind": "choice", "locations": [{"page": f["page"], "x": f["x"], "y": f["y"],
                                                         "grid": f.get("grid", "")}],
                "title": f"Markup note at p{f['page']} {f.get('grid', '')}: {f['text'][:40]}",
                "question": f"The drawing has a markup note \"{f['text']}\" at {_loc_text(f)}. "
                            + (f"Nearby: {f['context']}. " if f.get("context") else "")
                            + "Does it need a material on the BOM?",
                "why": "Notes like REPLACE or REPAIR are written in the markup but don't say which item is "
                       "affected or what material is needed, so the scan can't add it by itself.",
                "choices": [("add", "Yes - add an item (fill in below)"),
                            ("covered", "No - already covered by an item on the BOM"),
                            (NO_CHANGE, "No - nothing to buy for this note")],
                "fields": [{"key": "description", "label": "Item description", "default": f["text"].title()[:60]},
                           {"key": "qty", "label": "Quantity", "default": "1"}]}

    if t == "piping_runs":
        rows = [m for m in materials if m.get("type") == "piping"]
        if not rows:
            return None
        return {**base, "kind": "form", "locations": [l for m in rows for l in m.get("locations", [])],
                "title": "Piping lengths needed",
                "question": "Highlighted new piping is listed as runs, not footage. Enter the total length (feet) "
                            "for each size. Leave blank to keep it as a run count.",
                "why": "The drawing has no scale the scan can measure, so it can show where the piping is and its "
                       "size, but not how many feet to order.",
                "choices": [],
                "fields": [{"key": m["uid"], "label": f"{m['description']} ({m['quantity']} runs) - length in ft",
                            "default": ""} for m in rows]}

    if t == "unidentified_tags":
        tags = f.get("tags") or []
        return {**base, "kind": "form", "title": f"Unrecognised tags ({len(tags)})",
                "question": "These tag-like labels on the new-work pages weren't recognised by the legend. If one "
                            "is real equipment, enter what it is to add it to the BOM; leave blank to ignore it.",
                "why": "Their prefix isn't in the legend, the instrument key or the standard code list, so the scan "
                       "can't tell what they are.",
                "choices": [], "fields": [{"key": t_, "label": t_, "default": ""} for t_ in tags]}

    if t in ("no_text_layer", "legend_not_parsed", "tag_not_in_scope", "scope_tag_not_found",
             "scope_item_without_tag") or f.get("severity") in ("warning", "review"):
        return {**base, "kind": "choice", "title": f.get("message", "")[:70],
                "question": f.get("message", ""),
                "why": "The scan found something it can't resolve on its own. Your answer is recorded on the BOM; "
                       "add or edit items in the table if it changes what is needed.",
                "choices": [("ack", "Reviewed - no change needed"),
                            ("manual", "Needs manual BOM changes (I'll edit the table)")]}
    return None


def _new_item(q: dict, **kw) -> dict:
    item = {"item_number": 0, "uid": uuid.uuid4().hex[:8], "tag_id": "-", "unit": "ea", "confidence": 1.0,
            "origin": "user", "highlighted": False, "question_id": q["id"], "locations": [], "location": "",
            "pages": ""}
    item.update(kw)
    return item


def apply_answer(materials: list[dict], q: dict, answer: dict) -> dict:
    """Apply `answer` ({choice, checks, fields, comment}) to `materials` in place.

    Returns the record to store: question text, answer text, what changed, and undo data.
    """
    undo = {"remove_question": q["id"], "restore": []}
    changes: list[str] = []
    choice = answer.get("choice")
    fields = answer.get("fields") or {}

    def add(item):
        materials.append(item)
        changes.append(f"added {item['description']} x{item['quantity']}")

    if q["flag_type"] == "named_in_scope_but_existing" and choice == "add":
        it = q["items"][0]
        add(_new_item(q, tag_id=it["tag"], description=it["description"], type=it["type"], quantity=1,
                      location=it["location"], locations=it["locations"], pages=",".join(map(str, it["pages"])),
                      basis=f"added after review: scope names {it['tag']} although it is drawn as existing"))

    elif q["kind"] == "checklist":
        for it in q["items"]:
            if it["tag"] in (answer.get("checks") or []):
                add(_new_item(q, tag_id=it["tag"], description=it["description"], type=it["type"],
                              quantity=it["quantity"], location=it["location"], locations=it["locations"],
                              pages=",".join(map(str, it["pages"])),
                              basis="added after review: confirmed needed although excluded by the scan"))

    elif q["flag_type"] == "count_mismatch" and choice in ("scope", "drawing", "other"):
        flag_codes = set(q.get("codes") or [])
        rows = [m for m in materials if m.get("origin") == "drawing" and m.get("tag_id", "-").split("-")[0] in flag_codes]
        target = {"scope": q.get("scope_qty"), "other": _num(fields.get("qty"))}.get(choice)
        if target is not None and rows:
            others = sum(m["quantity"] for m in rows[1:])
            new_qty = max(0, target - others)
            undo["restore"].append({"uid": rows[0]["uid"], "quantity": rows[0]["quantity"]})
            rows[0]["quantity"] = new_qty
            rows[0]["basis"] = rows[0].get("basis", "") + f"; quantity set to match answer ({choice})"
            changes.append(f"{rows[0]['description']} quantity set to {new_qty}")

    elif q["flag_type"] == "markup_note" and choice == "add":
        loc = q["locations"][0]
        add(_new_item(q, description=fields.get("description") or q["title"], type="markup_item",
                      quantity=_num(fields.get("qty")) or 1, locations=[loc],
                      location=f"p{loc['page']} {loc.get('grid', '')}".strip(),
                      pages=str(loc["page"]), basis=f"added after review: markup note at that location"))

    elif q["flag_type"] == "piping_runs":
        by_uid = {m["uid"]: m for m in materials}
        for uid, text in fields.items():
            length = _num(text)
            if length and uid in by_uid:
                m = by_uid[uid]
                undo["restore"].append({"uid": uid, "quantity": m["quantity"], "unit": m["unit"]})
                m["quantity"], m["unit"] = length, "ft"
                m["basis"] = m.get("basis", "") + "; length entered at review"
                changes.append(f"{m['description']} set to {length} ft")

    elif q["flag_type"] == "unidentified_tags":
        for tag, desc in fields.items():
            if desc.strip():
                add(_new_item(q, tag_id=tag, description=desc.strip(), type="equipment", quantity=1,
                              basis="added after review: tag not recognised by the scan, identified by user"))

    answer_text = dict(q.get("choices") or []).get(choice, "")
    if q["kind"] == "checklist":
        answer_text = "Added: " + ", ".join(answer.get("checks") or []) if answer.get("checks") else "None needed"
    elif q["kind"] == "form" and not changes:
        answer_text = "No entries"
    elif q["kind"] == "form":
        answer_text = "; ".join(changes)
    return {"id": q["id"], "title": q["title"], "question": q["question"], "answer": answer_text,
            "comment": (answer.get("comment") or "").strip(), "effect": "; ".join(changes) or "no BOM change",
            "choice": choice, "input": answer, "undo": undo}


def undo_answer(materials: list[dict], record: dict) -> None:
    """Reverse what a previous answer did so it can be answered again."""
    undo = record.get("undo") or {}
    materials[:] = [m for m in materials if m.get("question_id") != undo.get("remove_question")]
    by_uid = {m.get("uid"): m for m in materials}
    for r in undo.get("restore", []):
        m = by_uid.get(r["uid"])
        if m:
            m["quantity"] = r["quantity"]
            if "unit" in r:
                m["unit"] = r["unit"]


def record_lines(answers: dict) -> list[str]:
    out = []
    for r in answers.values():
        line = f"Q: {r['title']} - A: {r['answer']}"
        if r.get("comment"):
            line += f" ({r['comment']})"
        if r.get("effect") and r["effect"] != "no BOM change":
            line += f" -> {r['effect']}"
        out.append(line)
    return out


def _num(value) -> float | int | None:
    try:
        n = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return int(n) if n == int(n) else n
