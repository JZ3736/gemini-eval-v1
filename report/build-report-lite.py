#!/usr/bin/env python3
"""
Lite report builder for the build-eval / hillclimb loop (Python 3 standard library only):
a single static report.html with no vendored runtime, fonts, or markdown engine.

  python3 build-report-lite.py .antigravity/hillclimb/<flow>/

Reads the same on-disk layout as build-report-lite.mjs (baseline/, v<N>/,
results.jsonl, errors.jsonl, change.md, summary.json, traces/, _state.json)
and derives the exact same numbers: per-variant mean of the primary metric over
status-ok rows, per-case means, split (train/val/test) from _state.json,
failed-attempt counts from errors.jsonl, and writes trajectory/scores.tsv.
"""

import datetime
import errno
import html as html_lib
import json
import math
import os
import re
import stat
import sys
from typing import Any, Dict, List, Optional, Tuple

WIN = sys.platform == "win32"
NOFOLLOW = 0 if WIN else getattr(os, "O_NOFOLLOW", 0)

ESC_SEQ = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?|\x1b[@-_]")
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")

def term_safe(s: Any) -> str:
    return CONTROL.sub("", ESC_SEQ.sub("", str(s)))

def eprint(*args: Any) -> None:
    print(*(term_safe(a) for a in args), file=sys.stderr, flush=True)

def is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)

def is_symlink(p: str) -> bool:
    try:
        return stat.S_ISLNK(os.lstat(p).st_mode)
    except OSError as e:
        if e.errno == errno.ENOENT:
            return False
        raise

SKIPPED_HARD_LINKS: List[str] = []

def read_text(p: str) -> str:
    fd: Optional[int] = None
    try:
        if WIN and is_symlink(p):
            return ""
        fd = os.open(p, os.O_RDONLY | NOFOLLOW)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return ""
        if st.st_nlink > 1:
            SKIPPED_HARD_LINKS.append(p)
            return ""
        chunks: List[bytes] = []
        while True:
            b = os.read(fd, 65536)
            if not b:
                break
            chunks.append(b)
        return b"".join(chunks).decode("utf-8")
    except Exception:
        return ""
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass

def read_json(p: str, dflt: Any) -> Any:
    try:
        txt = read_text(p)
        return json.loads(txt) if txt else dflt
    except Exception:
        return dflt

def assert_contained(dir_path: str, root: str) -> None:
    if not root:
        raise RuntimeError("refusing to write: output root not resolved")
    dir_real = os.path.realpath(dir_path)
    sep = "\\" if WIN else "/"
    if dir_real != root and not dir_real.startswith(root + sep):
        raise RuntimeError(f"refusing to write outside {root}: {dir_path}")

def resolve_output_root(root_arg: str) -> str:
    sep_pattern = r"(.)[\\/]+$" if WIN else r"(.)/+$"
    root = re.sub(sep_pattern, r"\1", str(root_arg))
    segments = re.split(r"[\\/]" if WIN else r"/", root)
    if any(seg in (".", "..") for seg in segments):
        raise RuntimeError(f"refusing to write into {root}: '.'/'..' path segment")
    if not os.path.isabs(root):
        walk = ""
        non_empty = [seg for seg in segments if seg]
        for part in non_empty[:-1]:
            walk = os.path.join(walk, part) if walk else part
            if is_symlink(walk):
                raise RuntimeError(f"refusing to write into {root}: ancestor {walk} is a symlink")
    if is_symlink(root):
        raise RuntimeError(f"refusing to write into {root}: it is a symlink")
    return os.path.realpath(root)

def write_no_follow(p: str, data: str, root: str) -> None:
    parent = os.path.dirname(p) or "."
    if is_symlink(parent):
        raise RuntimeError(f"refusing to write through symlinked directory: {parent}")
    assert_contained(parent, root)
    if WIN and is_symlink(p):
        raise RuntimeError(f"refusing to write through symlink: {p}")
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | NOFOLLOW, 0o644)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise RuntimeError(f"refusing to write to non-regular file: {p}")
        if st.st_nlink > 1:
            raise RuntimeError(
                f"refusing to write to {p}: it has a second hard link (another name for the same file); "
                "replace it with a plain copy if it is yours"
            )
        os.ftruncate(fd, 0)
        buf = data.encode("utf-8")
        view = memoryview(buf)
        while view:
            n = os.write(fd, view)
            if n <= 0:
                raise RuntimeError(f"write to {p} made no progress")
            view = view[n:]
    finally:
        os.close(fd)

def mkdir_no_follow(dir_path: str, root: str) -> None:
    if is_symlink(dir_path):
        raise RuntimeError(f"refusing to use symlinked directory: {dir_path}")
    os.makedirs(dir_path, exist_ok=True)
    assert_contained(dir_path, root)

def esc(s: Any) -> str:
    return (
        str("" if s is None else s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )

def fmt(x: Optional[float]) -> str:
    return "" if x is None else f"{x:.3f}"

def tsv_cell(s: Any) -> str:
    flat = re.sub(r"[\t\n\r]", " ", str(s))
    return ("'" + flat) if re.match(r"^[=+\-@]", flat) else flat

def discover_variants(flow: str) -> List[str]:
    names = [
        e.name
        for e in os.scandir(flow)
        if e.is_dir(follow_symlinks=False) and re.match(r"^(baseline|v\d+)$", e.name)
    ]
    def rank(n: str) -> int:
        return -1 if n == "baseline" else int(n[1:])
    return sorted(names, key=rank)

def coerce_scores(g: Any) -> Dict[str, float]:
    if isinstance(g, dict):
        out: Dict[str, float] = {}
        for k, v in g.items():
            if isinstance(v, bool):
                out[k] = 1.0 if v else 0.0
            elif is_num(v):
                out[k] = float(v)
        return out
    if isinstance(g, bool):
        return {"score": 1.0 if g else 0.0}
    if is_num(g):
        return {"score": float(g)}
    return {}

def load_rows(p: str, warnings: List[str], dir_name: str) -> Dict[str, List[Dict[str, Any]]]:
    by_id: Dict[str, List[Dict[str, Any]]] = {}
    for i, raw_line in enumerate(read_text(p).split("\n")):
        line = raw_line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            warnings.append(f"{dir_name}/results.jsonl:{i + 1}: malformed JSON, skipped")
            continue
        pid = str(r.get("prompt_id") or r.get("id") or r.get("case_id") or "")
        if not pid:
            warnings.append(f"{dir_name}/results.jsonl:{i + 1}: no prompt_id, skipped")
            continue
        by_id.setdefault(pid, []).append(r)
    return by_id

def count_errors(vdir: str) -> Dict[str, Any]:
    total = 0
    by_class: Dict[str, int] = {}
    for line in read_text(os.path.join(vdir, "errors.jsonl")).split("\n"):
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        total += 1
        c = str(e.get("failure_class") or "error")
        by_class[c] = by_class.get(c, 0) + 1
    return {"total": total, "byClass": by_class}

def infer_metrics(rows: Dict[str, Dict[str, List[Dict[str, Any]]]], variants: List[str]) -> List[Dict[str, str]]:
    seen: Dict[str, Dict[str, bool]] = {}
    for v in variants:
        for reps in rows[v].values():
            for r in reps:
                expl = r.get("explanation") if isinstance(r.get("explanation"), dict) else {}
                for k, val in coerce_scores(r.get("grade")).items():
                    m = seen.setdefault(k, {"binary": True, "judge": False})
                    if val != 0.0 and val != 1.0:
                        m["binary"] = False
                    if k in expl:
                        m["judge"] = True
    return [
        {"id": k, "kind": "judge" if s["judge"] else ("binary" if s["binary"] else "float")}
        for k, s in seen.items()
    ]

CSS = "".join([
    ":root{color-scheme:light dark;--fg:#1a1a1a;--bg:#fff;--muted:#666;--line:#ddd;--pill:#eee;--warn:#b45309;--best:#ecfdf5}",
    "@media(prefers-color-scheme:dark){:root{--fg:#e6e6e6;--bg:#121212;--muted:#9a9a9a;--line:#333;--pill:#2a2a2a;--warn:#f59e0b;--best:#0f2a1f}}",
    "body{font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--fg);background:var(--bg);margin:0;padding:24px;max-width:1400px}",
    "h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px}.meta,.hint{color:var(--muted);margin:0 0 8px}",
    "table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}",
    'th{cursor:pointer;user-select:none;white-space:nowrap}th.asc:after{content:" \\25B4"}th.desc:after{content:" \\25BE"}',
    "td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}td.id{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;white-space:nowrap}",
    ".pill{display:inline-block;background:var(--pill);border-radius:10px;padding:0 8px;font-size:12px}.pill.warn{color:var(--warn)}",
    "tr.best td{background:var(--best)}.links{font-size:12px}.links a{margin-right:6px}",
    "td.prompt{max-width:520px}details summary{cursor:pointer;color:var(--muted)}pre{white-space:pre-wrap;font-size:12px;margin:6px 0 0}",
    ".warnings{color:var(--warn)}code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}",
])

SORT_JS = "".join([
    'document.querySelectorAll("th[data-k]").forEach(function(th){th.addEventListener("click",function(){',
    'var t=th.closest("table"),tb=t.tBodies[0],i=Array.prototype.indexOf.call(th.parentNode.children,th);',
    'var asc=!th.classList.contains("asc");t.querySelectorAll("th").forEach(function(h){h.classList.remove("asc","desc")});',
    'th.classList.add(asc?"asc":"desc");var num=th.dataset.k==="n";',
    'var rows=Array.prototype.slice.call(tb.rows);rows.sort(function(a,b){var x=a.cells[i],y=b.cells[i];',
    'var u=num?parseFloat("v" in x.dataset?x.dataset.v:x.textContent):x.textContent.trim().toLowerCase();',
    'var w=num?parseFloat("v" in y.dataset?y.dataset.v:y.textContent):y.textContent.trim().toLowerCase();',
    'if(num){if(isNaN(u))u=-Infinity;if(isNaN(w))w=-Infinity}return (u<w?-1:u>w?1:0)*(asc?1:-1)});',
    'rows.forEach(function(r){tb.appendChild(r)})})});',
])

def render(
    flow: str,
    variants: List[str],
    header: Dict[str, Any],
    agg: Dict[str, Any],
    cases: List[Dict[str, Any]],
    primary: str,
    metrics: List[str],
    warnings: List[str],
    best: Optional[str],
) -> str:
    has_split = any(c["split"] for c in cases)
    has_test = any(agg[v]["nTest"] > 0 for v in variants)
    def th(label: str, key: str) -> str:
        return f'<th data-k="{esc(key)}">{esc(label)}</th>'

    variant_rows_list: List[str] = []
    for v in variants:
        h = header[v]
        a = agg[v]
        err = (
            f"{h['errors']['total']} ("
            + ", ".join(f"{esc(k)} {n}" for k, n in h["errors"]["byClass"].items())
            + ")"
            if h["errors"]["total"]
            else "0"
        )
        best_cls = ' class="best"' if best == v else ""
        best_pill = ' <span class="pill">best</span>' if best == v else ""
        test_cols = f'<td class="num">{fmt(a["test"])}</td><td class="num">{a["nTest"]}</td>' if has_test else ""
        variant_rows_list.append(
            f"<tr{best_cls}><td>{esc(v)}{best_pill}</td>"
            f"<td>{esc(h['change'])}</td><td>{esc(h['model'])}</td>"
            f'<td class="num">{fmt(a["all"])}</td><td class="num">{a["n"]}</td>'
            f"{test_cols}"
            f'<td class="num">{a["truncated"]}</td><td>{err}</td></tr>'
        )
    variant_rows = "\n".join(variant_rows_list)

    case_rows_list: List[str] = []
    for c in cases:
        cells_list: List[str] = []
        for v in variants:
            p = c["per"][v]
            links = " ".join(f'<a href="{esc(t["rel"])}">rep{esc(t["rep"])}</a>' for t in p["traces"])
            trunc_html = f' <span class="pill warn">{p["truncated"]} truncated</span>' if p["truncated"] else ""
            links_html = f'<div class="links">{links}</div>' if links else ""
            cells_list.append(
                f'<td class="num" data-v="{fmt(p["mean"])}">{fmt(p["mean"])}{trunc_html}{links_html}</td>'
            )
        cells = "".join(cells_list)
        prompt = c["prompt"][:600] + "..." if len(c["prompt"]) > 600 else c["prompt"]
        first_line = prompt.split("\n")[0][:80]
        split_col = f"<td>{esc(c['split'])}</td>" if has_split else ""
        tags_html = " ".join(f'<span class="pill">{esc(t)}</span>' for t in c["tags"])
        case_rows_list.append(
            f'<tr><td class="id">{esc(c["id"])}</td>'
            f"{split_col}"
            f"<td>{tags_html}</td>"
            f"{cells}"
            f'<td class="prompt"><details><summary>{esc(first_line)}</summary><pre>{esc(prompt)}</pre></details></td></tr>'
        )
    case_rows = "\n".join(case_rows_list)

    warn = (
        '<section class="warnings"><h2>Warnings</h2><ul>'
        + "".join(f"<li>{esc(w)}</li>" for w in warnings)
        + "</ul></section>"
        if warnings
        else ""
    )

    flow_name = re.split(r"[\\/]", flow)[-1]
    also_metrics = (
        " (also: " + ", ".join(esc(m) for m in metrics if m != primary) + ")"
        if len(metrics) > 1
        else ""
    )
    now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{esc(flow_name)} - eval report</title>"
        f"<style>{CSS}</style></head><body>"
        f"<header><h1>{esc(flow_name)}</h1>"
        f'<p class="meta">{len(variants)} variant{"" if len(variants) == 1 else "s"} &middot; {len(cases)} cases'
        f" &middot; primary metric <code>{esc(primary)}</code>"
        f"{also_metrics}"
        f" &middot; generated {now_utc} UTC"
        " &middot; lite report (no transcripts inlined; click rep links)</p></header>"
        "<section><h2>Variants</h2><table><thead><tr>"
        + th("variant", "s")
        + th("change", "s")
        + th("model", "s")
        + th("mean " + primary, "n")
        + th("cases", "n")
        + (th("test mean", "n") + th("test cases", "n") if has_test else "")
        + th("truncated", "n")
        + th("failed attempts", "s")
        + f"</tr></thead><tbody>{variant_rows}</tbody></table></section>"
        f'<section><h2>Cases</h2><p class="hint">Click a column header to sort. Per-case values are the mean of <code>{esc(primary)}</code> over status-ok reps.</p>'
        '<table id="cases"><thead><tr>'
        + th("id", "s")
        + (th("split", "s") if has_split else "")
        + th("tags", "s")
        + "".join(th(v, "n") for v in variants)
        + th("prompt", "s")
        + f"</tr></thead><tbody>{case_rows}</tbody></table></section>"
        f"{warn}"
        f"<script>{SORT_JS}</script></body></html>\n"
    )

def build(flow_arg: str) -> Dict[str, Any]:
    flow = os.path.abspath(flow_arg)
    if not os.path.isdir(flow):
        raise RuntimeError("not a directory: " + flow)
    flow_root = resolve_output_root(flow_arg)
    variants = discover_variants(flow)
    if not variants:
        raise RuntimeError("no variant directories (baseline/, v1/, ...) under " + flow)
    warnings: List[str] = []
    non_variant = {"trajectory", "attachments", "refs", "ref", "inputs", "out", "target", "__pycache__"}
    for e in os.scandir(flow):
        if (
            e.is_dir(follow_symlinks=False)
            and e.name not in variants
            and e.name not in non_variant
            and not e.name.startswith(".")
            and not e.name.startswith("_")
        ):
            warnings.append(
                f"ignored directory '{e.name}/' - variant dirs must be named 'baseline' or 'v<N>'; "
                "put the descriptive name in change.md's first line instead"
            )

    state = read_json(os.path.join(flow, "_state.json"), {}) or {}
    split_of: Dict[str, str] = {}
    for sp in ("train", "val", "test"):
        ids = state.get(sp + "_ids")
        if ids is None:
            continue
        if not isinstance(ids, list):
            warnings.append(f"_state.json {sp}_ids is not a list - ignored")
            continue
        for pid in ids:
            split_of[str(pid)] = sp

    rows: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for v in variants:
        rows[v] = load_rows(os.path.join(flow, v, "results.jsonl"), warnings, v)

    trace_dir_ok: Dict[str, bool] = {}
    sep = "\\" if WIN else "/"
    for v in variants:
        tdir = os.path.join(flow, v, "traces")
        try:
            if is_symlink(os.path.join(flow, v)) or is_symlink(tdir):
                warnings.append(f"{v}/traces is reached through a symlink - trace links omitted")
                trace_dir_ok[v] = False
            else:
                real = os.path.realpath(tdir)
                trace_dir_ok[v] = real.startswith(flow_root + sep)
        except Exception:
            trace_dir_ok[v] = False

    for i in range(len(variants) - 1, 0, -1):
        v = variants[i]
        if rows[v]:
            continue
        warnings.append(f"{v}: zero result rows - dropping (run not started or results.jsonl missing/empty)")
        variants.pop(i)

    if not rows[variants[0]]:
        extra = (
            " (not read, second hard link: "
            + ", ".join(p[len(flow) + 1 :] for p in SKIPPED_HARD_LINKS)
            + " - replace with plain copies if they are yours)"
            if SKIPPED_HARD_LINKS
            else ""
        )
        raise RuntimeError(f"{variants[0]}/ has no result rows under {flow} - nothing to report{extra}")

    header: Dict[str, Any] = {}
    for v in variants:
        vdir = os.path.join(flow, v)
        change_lines = [l.strip() for l in read_text(os.path.join(vdir, "change.md")).split("\n") if l.strip()]
        change = re.sub(r"^#+\s*", "", change_lines[0]) if change_lines else ""
        summary = read_json(os.path.join(vdir, "summary.json"), {}) or {}
        tally: Dict[str, int] = {}
        for reps in rows[v].values():
            for r in reps:
                m = r.get("model")
                if isinstance(m, str):
                    tally[m] = tally.get(m, 0) + 1
        row_model = sorted(tally.items(), key=lambda x: x[1], reverse=True)[0][0] if tally else ""
        header[v] = {
            "change": change,
            "model": summary.get("model") or row_model,
            "errors": count_errors(vdir),
        }

    metrics_cfg = state.get("metrics") or state.get("criteria")
    declared: List[Dict[str, Any]] = []
    if isinstance(metrics_cfg, list):
        for m in metrics_cfg:
            if isinstance(m, str) and m:
                declared.append({"id": m, "kind": None})
            elif isinstance(m, dict) and m.get("id"):
                declared.append({"id": str(m["id"]), "kind": m.get("kind")})

    metrics = declared if declared else infer_metrics(rows, variants)
    if not metrics:
        metrics.append({"id": "score", "kind": "float"})
    primary_metric = next((m for m in metrics if m.get("kind") == "binary"), metrics[0])["id"]

    ids: List[str] = []
    seen_id = set()
    for v in variants:
        for pid in rows[v].keys():
            if pid not in seen_id:
                seen_id.add(pid)
                ids.append(pid)

    def ok_reps(reps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [r for r in reps if r.get("status") is None or r.get("status") == "ok"]

    def case_mean(reps: List[Dict[str, Any]], m: str) -> Optional[float]:
        vals = [coerce_scores(r.get("grade")).get(m) for r in ok_reps(reps)]
        num_vals = [x for x in vals if is_num(x)]
        return sum(num_vals) / len(num_vals) if num_vals else None

    cases: List[Dict[str, Any]] = []
    for pid in ids:
        first = next((rows[v][pid][0] for v in variants if rows[v].get(pid)), {})
        tags = [str(t) for t in first.get("tags", [])] if isinstance(first.get("tags"), list) else []
        per: Dict[str, Any] = {}
        for v in variants:
            reps = rows[v].get(pid, [])
            traces: List[Dict[str, Any]] = []
            for k, r in enumerate(reps):
                if not trace_dir_ok.get(v):
                    continue
                rep = r.get("rep", k)
                if not re.match(r"^[A-Za-z0-9_.-]+$", pid) or re.match(r"^\.+$", pid):
                    continue
                try:
                    rep_int = int(rep)
                except (ValueError, TypeError):
                    continue
                if rep_int < 0:
                    continue
                stems = [f"{pid}_rep{rep_int}", pid] if rep_int == 0 else [f"{pid}_rep{rep_int}"]
                for stem in stems:
                    rel = f"{v}/traces/{stem}.json"
                    abs_p = os.path.abspath(os.path.join(flow, rel))
                    if os.path.dirname(abs_p) != os.path.join(flow, v, "traces"):
                        break
                    try:
                        ls = os.lstat(abs_p)
                        if stat.S_ISREG(ls.st_mode) and ls.st_nlink <= 1:
                            traces.append({"rep": rep_int, "rel": rel})
                            break
                    except OSError:
                        pass
            per[v] = {
                "mean": case_mean(reps, primary_metric),
                "reps": len(reps),
                "truncated": sum(1 for r in reps if r.get("status") == "truncated"),
                "traces": traces,
            }
        cases.append({
            "id": pid,
            "split": split_of.get(pid, ""),
            "tags": tags,
            "prompt": str(first.get("prompt") or ""),
            "per": per,
        })

    agg: Dict[str, Any] = {}
    for v in variants:
        all_vals = [c["per"][v]["mean"] for c in cases if is_num(c["per"][v]["mean"])]
        test_vals = [c["per"][v]["mean"] for c in cases if c["split"] == "test" and is_num(c["per"][v]["mean"])]
        agg[v] = {
            "all": (sum(all_vals) / len(all_vals)) if all_vals else None,
            "n": len(all_vals),
            "test": (sum(test_vals) / len(test_vals)) if test_vals else None,
            "nTest": len(test_vals),
            "truncated": sum(c["per"][v]["truncated"] for c in cases),
        }

    mkdir_no_follow(os.path.join(flow, "trajectory"), flow_root)
    tsv = ["\t".join(["id", "split", *variants])]
    for c in cases:
        tsv.append(
            "\t".join([
                tsv_cell(c["id"]),
                tsv_cell(c["split"] or "all"),
                *(fmt(c["per"][v]["mean"]) for v in variants),
            ])
        )
    write_no_follow(os.path.join(flow, "trajectory", "scores.tsv"), "\n".join(tsv) + "\n", flow_root)

    best: Optional[str] = None
    best_round = state.get("best", {}).get("round") if isinstance(state.get("best"), dict) else None
    if isinstance(best_round, int) and not isinstance(best_round, bool):
        cand = "baseline" if best_round == 0 else f"v{best_round}"
        if cand in variants:
            best = cand

    for p in dict.fromkeys(SKIPPED_HARD_LINKS):
        warnings.append(f"{p[len(flow) + 1:]} has a second hard link - not read; replace it with a plain copy if it is yours")

    html_out = render(
        flow=flow,
        variants=variants,
        header=header,
        agg=agg,
        cases=cases,
        primary=primary_metric,
        metrics=[m["id"] for m in metrics],
        warnings=warnings,
        best=best,
    )
    write_no_follow(os.path.join(flow, "report.html"), html_out, flow_root)
    return {"variants": len(variants), "cases": len(cases), "warnings": warnings}

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if not arg or arg in ("-h", "--help"):
        eprint("usage: python3 build-report-lite.py <flow-dir>   (e.g. .antigravity/hillclimb/<flow>/)")
        sys.exit(0 if arg else 2)
    try:
        res = build(arg)
        for w in res["warnings"]:
            eprint("warning: " + w)
        eprint(
            f"wrote {os.path.join(os.path.abspath(arg), 'report.html')} "
            f"({res['variants']} variants, {res['cases']} cases) and trajectory/scores.tsv"
        )
    except Exception as exc:
        eprint("build-report-lite: " + str(exc))
        sys.exit(1)
