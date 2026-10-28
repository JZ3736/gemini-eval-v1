#!/usr/bin/env python3
"""
Runner scaffold for the build-eval / hillclimb loop (Python 3 standard library only).
Copy this into the user's repo and fill in load_cases / run_case / grade_case below -
the I/O shape, file naming, resume, and CLI surface are already hillclimb-ready
so adding v2, v3, ... is `--variant v3`, not a refactor.

  python3 run-eval.py --flow .antigravity/hillclimb/<name> --variant baseline --reps 2

Structural properties this encodes (100% parity with runner-scaffold.mjs):
  - parameterized by --variant / --model / --reps (no hardcoded A/B pair)
  - rep-aware filenames + resume (traces/<id>_rep<k>.json)
  - reads _state.json, never writes it (loop state belongs to the orchestrator) -
    the ONE exception is --approve-harness recording `harness_sha` (see below)
  - refuses to run when the harness (this file + lockfiles + _state.json.harness_paths)
    has changed since the sha a human last approved with --approve-harness
  - pairwise graders judge against frozen baseline/ref/<id>.* on disk
  - writes rows as cases complete (crash-safe)
  - jittered exponential backoff on transient 429/overloaded/5xx errors
  - hard per-case wall-clock ceiling (--timeout-s; stream keepalives don't reset it)
  - served-model assertion across Gemini (gemini-4-pro, gemini-3.8-flash, gemini-2.5-*)
    and Vertex AI Model Garden / Anthropic / OpenAI-compatible model IDs
  - failed attempts land in errors.jsonl with a failure class and, when the call
    completed, the billed model/usage (never in results.jsonl)
  - row ids, trace filenames, and frozen refs share one path-safe id
    (original id kept in meta.original_id when sanitization changed it)
"""

import asyncio
import errno
import hashlib
import json
import math
import os
import random
import re
import stat
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

WIN = sys.platform == "win32"
NOFOLLOW = 0 if WIN else getattr(os, "O_NOFOLLOW", 0)

ESC_SEQ = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?|\x1b[@-_]")
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")

def term_safe(s: Any) -> str:
    return CONTROL.sub("", ESC_SEQ.sub("", str(s)))

def eprint(*args: Any) -> None:
    print(*(term_safe(a) for a in args), file=sys.stderr, flush=True)

def lstat_or_null(p: str) -> Optional[os.stat_result]:
    try:
        return os.lstat(p)
    except OSError as e:
        if e.errno == errno.ENOENT:
            return None
        raise

def is_symlink(p: str) -> bool:
    st = lstat_or_null(p)
    return bool(st is not None and stat.S_ISLNK(st.st_mode))

FLOW_REAL_ROOT: Optional[str] = None

def assert_in_flow(dir_path: str, what: str) -> None:
    if FLOW_REAL_ROOT is None:
        raise RuntimeError(f"refusing to {what}: flow root not resolved yet")
    dir_real = os.path.realpath(dir_path)
    sep = "\\" if WIN else "/"
    if dir_real != FLOW_REAL_ROOT and not dir_real.startswith(FLOW_REAL_ROOT + sep):
        raise RuntimeError(f"refusing to {what}: {dir_path} resolves outside the flow directory")

def open_no_follow(p: str, flags: int) -> int:
    parent = os.path.dirname(p) or "."
    if is_symlink(parent):
        raise RuntimeError(f"refusing to open through symlinked directory: {parent}")
    assert_in_flow(parent, "open")
    if WIN and is_symlink(p):
        raise RuntimeError(f"refusing to open through symlink: {p}")
    fd = os.open(p, flags | NOFOLLOW, 0o644)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise RuntimeError(f"refusing to use non-regular file: {p}")
        if st.st_nlink > 1:
            raise RuntimeError(
                f"refusing to use {p}: it has a second hard link (another name for the same file); "
                "replace it with a plain copy if it is yours"
            )
    except Exception:
        os.close(fd)
        raise
    return fd

def write_file_no_follow(p: str, data: str) -> None:
    fd = open_no_follow(p, os.O_WRONLY | os.O_CREAT)
    try:
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

def append_file_no_follow(p: str, data: str) -> None:
    fd = open_no_follow(p, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    try:
        buf = data.encode("utf-8")
        view = memoryview(buf)
        while view:
            n = os.write(fd, view)
            if n <= 0:
                raise RuntimeError(f"append to {p} made no progress")
            view = view[n:]
    finally:
        os.close(fd)

def lexists(p: str) -> bool:
    return lstat_or_null(p) is not None

def read_file_no_follow(p: str) -> str:
    fd = open_no_follow(p, os.O_RDONLY)
    try:
        chunks: List[bytes] = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8")
    finally:
        os.close(fd)

def read_if_present(p: str) -> Optional[str]:
    try:
        return read_file_no_follow(p)
    except OSError as e:
        if e.errno == errno.ENOENT:
            return None
        raise

def mkdir_no_follow(dir_path: str) -> None:
    if is_symlink(dir_path):
        raise RuntimeError(f"refusing to use symlinked directory: {dir_path}")
    os.makedirs(dir_path, exist_ok=True)
    assert_in_flow(dir_path, "create directory")

REF_EXTS = ["", ".html", ".txt", ".json"]

# --- fill these in ----------------------------------------------------------

async def load_cases() -> List[Dict[str, Any]]:
    """Return the list of input cases. Each must have a stable `id`."""
    # e.g. return json.loads(Path("eval/cases.json").read_text("utf-8"))
    raise NotImplementedError("TODO: load_cases")

async def run_case(input_case: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run the app on one input. Return everything the grader and the report need.
    `ctx["model"]` and `ctx["variant"]` are the CLI args; use them to pick the model
    and (for hillclimb) the harness/prompt under test.
    """
    # Example with google-genai or Vertex AI REST:
    # return {
    #   "output": response_text,
    #   "transcript": [
    #     {"role": "system", "content": system_instruction},
    #     {"role": "user", "content": input_case["prompt"]},
    #     {"role": "assistant", "content": response_text, "thinking": thought_text},
    #   ],
    #   "model": served_model_id,
    #   "usage": {
    #     "input_tokens": prompt_tokens,
    #     "output_tokens": candidate_tokens + thought_tokens,
    #     "cache_read_input_tokens": cached_tokens,
    #   },
    #   "stop_reason": finish_reason,  # e.g. "STOP" | "MAX_TOKENS" | "end_turn" | "max_tokens"
    # }
    raise NotImplementedError("TODO: run_case")

async def grade_case(
    input_case: Dict[str, Any],
    run: Dict[str, Any],
    ref: Optional[str],
    ctx: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Grade one output. For pairwise, `ref` is the FROZEN baseline output read
    from disk (baseline/ref/<id>.*) - never a freshly co-generated one.
    Return {"grade": {metric_id: number, ...}, "explanation": {metric_id: str},
            "judge_model": ..., "judge_usage": ...}.
    """
    # return {"grade": {"pass": 1 if input_case["expected"] in run["output"] else 0}}
    raise NotImplementedError("TODO: grade_case")

def perf_from(run: Dict[str, Any]) -> Dict[str, Any]:
    """Side-channel perf fields beyond the built-ins (latency_s etc.)."""
    return {}

# --- harness (you usually won't need to touch below this line) --------------

def usage() -> None:
    eprint(
        "usage: python3 run-eval.py --flow DIR --variant ID [--model ID] [--reps N] "
        "[--concurrency N] [--timeout-s N (0 = no ceiling)] [--approve-harness]"
    )

def parse_args(argv: List[str]) -> Dict[str, Any]:
    a: Dict[str, Any] = {
        "flow": ".antigravity/hillclimb/flow",
        "variant": "baseline",
        "model": None,
        "reps": 1,
        "concurrency": 4,
        "timeoutS": 1800.0,
        "approveHarness": False,
    }
    i = 0
    def val(idx: int) -> str:
        if idx >= len(argv):
            eprint(f"missing value for {argv[idx - 1]}")
            usage()
            sys.exit(2)
        return argv[idx]

    while i < len(argv):
        k = argv[i]
        if k == "--flow":
            i += 1
            a["flow"] = val(i)
        elif k == "--variant":
            i += 1
            a["variant"] = val(i)
        elif k == "--model":
            i += 1
            a["model"] = val(i)
        elif k == "--reps":
            i += 1
            try:
                a["reps"] = int(val(i))
            except ValueError:
                usage()
                sys.exit(2)
        elif k == "--concurrency":
            i += 1
            try:
                a["concurrency"] = int(val(i))
            except ValueError:
                usage()
                sys.exit(2)
        elif k == "--timeout-s":
            i += 1
            try:
                a["timeoutS"] = float(val(i))
            except ValueError:
                usage()
                sys.exit(2)
        elif k == "--approve-harness":
            a["approveHarness"] = True
        elif k in ("-h", "--help"):
            usage()
            sys.exit(0)
        else:
            eprint(f"unknown argument: {k}")
            usage()
            sys.exit(2)
        i += 1

    if not re.match(r"^(baseline|v[1-9]\d*)$", str(a["variant"])):
        eprint(f"--variant must be 'baseline' or 'v<N>', got '{a['variant']}'")
        usage()
        sys.exit(2)

    if (
        not math.isfinite(a["timeoutS"])
        or a["timeoutS"] < 0
        or a["timeoutS"] * 1000 > 2147483647
        or not isinstance(a["reps"], int)
        or a["reps"] < 1
        or not isinstance(a["concurrency"], int)
        or a["concurrency"] < 1
    ):
        usage()
        sys.exit(2)
    return a

def check_harness(state_path: str, st: Dict[str, Any], approve: bool) -> None:
    self_path = os.path.abspath(__file__)
    listed = [str(x) for x in st.get("harness_paths", [])] if isinstance(st.get("harness_paths"), list) else []
    lock_names = [
        "uv.lock",
        "poetry.lock",
        "Pipfile.lock",
        "requirements.txt",
        "package-lock.json",
        "bun.lock",
        "bun.lockb",
        "yarn.lock",
        "pnpm-lock.yaml",
    ]
    search_dirs = list(dict.fromkeys([os.path.dirname(self_path), os.getcwd()]))
    lockfiles = [
        os.path.join(d, f)
        for d in search_dirs
        for f in lock_names
        if os.path.exists(os.path.join(d, f))
    ]
    all_paths = sorted(set([self_path, *lockfiles, *(os.path.abspath(p) for p in listed)]))
    h = hashlib.sha256()
    hashed: List[str] = []
    cwd = os.getcwd()
    for p in all_paths:
        rel = os.path.relpath(p, cwd)
        try:
            with open(p, "rb") as f:
                buf = f.read()
        except OSError as e:
            if p == self_path:
                raise
            eprint(f"warning: harness path '{rel}' not readable ({e.strerror or 'error'}) - skipped")
            continue
        h.update(rel.encode("utf-8") + b"\0" + buf + b"\0")
        hashed.append(rel)

    sha = h.hexdigest()
    if st.get("harness_sha") == sha:
        return
    if not lockfiles:
        eprint("note: no lockfile beside the runner or in the current directory - dependency changes are outside the harness sha")
    if approve:
        st["harness_sha"] = sha
        write_file_no_follow(state_path, json.dumps(st, indent=2) + "\n")
        eprint(f"harness approved: sha256 {sha[:12]} over {len(hashed)} file(s) recorded in {state_path}")
        return
    if st.get("harness_sha") is None:
        eprint(f"no approved harness sha in {state_path} (computed {sha[:12]} over: {', '.join(hashed)}).")
        eprint("Review the harness, then run once with --approve-harness to record it.")
    else:
        eprint(
            f"harness changed since last approved run (files: {', '.join(hashed)}); "
            f"approved {str(st.get('harness_sha'))[:12]}, now {sha[:12]}."
        )
        eprint("Re-run with --approve-harness after reviewing the diff.")
    sys.exit(2)

class EvalFailure(Exception):
    def __init__(
        self,
        message: str,
        failure_class: str = "error",
        status: Optional[int] = None,
        judge_model: Optional[str] = None,
        judge_usage: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.failure_class = failure_class
        self.status = status
        self.judge_model = judge_model
        self.judge_usage = judge_usage

async def with_backoff(fn, retry: Dict[str, int], deadline: float = float("inf"), tries: int = 5):
    attempt = 0
    while True:
        if time.time() >= deadline:
            raise EvalFailure("wall-clock ceiling exceeded before attempt", failure_class="timeout")
        try:
            return await fn()
        except Exception as e:
            status = getattr(e, "status", None) or getattr(e, "code", None)
            msg = str(e)
            transient = (
                status in (429, 529)
                or (isinstance(status, int) and 500 <= status < 600)
                or bool(re.search(r"overloaded|rate.?limit|resource.?exhausted|quota|503|429", msg, re.I))
            )
            if not transient or attempt >= tries - 1:
                raise
            delay = min(60.0, (1.0 * (2 ** attempt))) * (0.5 + random.random())
            if time.time() + delay >= deadline:
                raise
            retry["count"] += 1
            await asyncio.sleep(delay)
            attempt += 1

async def with_timeout(coro, seconds: float, label: str):
    if not (seconds > 0):
        return await coro
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except asyncio.TimeoutError:
        raise EvalFailure(f"{label}: exceeded {seconds:g}s wall-clock ceiling", failure_class="timeout")

def path_safe_id(raw_id: Any) -> str:
    raw = str(raw_id)
    cleaned = re.sub(r"[^\w.-]", "_", raw, flags=re.ASCII)
    if cleaned == raw and len(raw) <= 129:
        return raw
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return f"{cleaned[:120]}-{digest}"

def normalize_model_base(model_id: str) -> str:
    """
    Normalize model IDs across Gemini (gemini-4-pro, gemini-3.8-flash, publishers/google/models/...),
    Anthropic/Vertex (@YYYYMMDD, -YYYYMMDD), and OpenAI/Model Garden prefixes.
    """
    m = str(model_id).strip()
    if "/models/" in m:
        m = m.split("/models/")[-1]
    elif "/" in m:
        m = m.split("/")[-1]
    m = re.sub(r"[-@](\d{8}|\d{4}-\d{2}-\d{2}|00\d|latest|0|exp.*|preview.*)$", "", m)
    return m

def check_served_model(requested: Optional[str], served: Optional[str]) -> None:
    if not requested or not served or requested == served:
        return
    req_base = normalize_model_base(requested)
    srv_base = normalize_model_base(served)
    if req_base != srv_base:
        raise EvalFailure(
            f"served model {served} != requested {requested}",
            failure_class="serving_substitution",
        )

WORKERS_STARTED = False

async def async_main() -> None:
    global FLOW_REAL_ROOT, WORKERS_STARTED
    args = parse_args(sys.argv[1:])
    sep_pattern = r"(.)[\\/]+$" if WIN else r"(.)/+$"
    args["flow"] = re.sub(sep_pattern, r"\1", args["flow"])
    flow_segments = re.split(r"[\\/]" if WIN else r"/", args["flow"])
    if any(seg in (".", "..") for seg in flow_segments):
        eprint(f"refusing to run: --flow must not contain '.' or '..' segments, got '{args['flow']}'")
        sys.exit(2)

    vdir = os.path.join(args["flow"], args["variant"])
    preflight_paths = [
        args["flow"],
        os.path.join(args["flow"], "baseline"),
        vdir,
        os.path.join(vdir, "traces"),
        os.path.join(vdir, "results.jsonl"),
        os.path.join(vdir, "errors.jsonl"),
        os.path.join(vdir, "progress.txt"),
        os.path.join(args["flow"], "baseline", "ref"),
        os.path.join(args["flow"], "_state.json"),
    ]
    for p in preflight_paths:
        if is_symlink(p):
            eprint(f"refusing to run: {p} is a symlink (the flow dir must hold regular files)")
            sys.exit(2)

    if not os.path.isabs(args["flow"]):
        walk = ""
        non_empty = [seg for seg in flow_segments if seg]
        for part in non_empty[:-1]:
            walk = os.path.join(walk, part) if walk else part
            if is_symlink(walk):
                eprint(f"refusing to run: {walk} is a symlink (ancestor of --flow)")
                sys.exit(2)

    os.makedirs(args["flow"], exist_ok=True)
    FLOW_REAL_ROOT = os.path.realpath(args["flow"])
    mkdir_no_follow(os.path.join(vdir, "traces"))

    state_path = os.path.join(args["flow"], "_state.json")
    st: Dict[str, Any] = {}
    state_text = read_if_present(state_path)
    if state_text is not None:
        try:
            parsed = json.loads(state_text)
            st = parsed if isinstance(parsed, dict) else {}
        except Exception:
            eprint(f"{state_path} exists but is not valid JSON - fix it before spending a pass")
            sys.exit(2)

    check_harness(state_path, st, args["approveHarness"])
    ctx = {**args, "state": st}

    results_path = os.path.join(vdir, "results.jsonl")
    done = set()
    for ln in (read_if_present(results_path) or "").split("\n"):
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
            done.add(f"{r.get('prompt_id')}\0{r.get('rep')}")
        except Exception:
            pass

    cases = await load_cases()
    seen: Dict[str, str] = {}
    for c in cases:
        k = path_safe_id(c["id"]).lower()
        if k in seen:
            eprint(f"duplicate case id after sanitization: '{c['id']}' collides with '{seen[k]}'")
            sys.exit(2)
        seen[k] = str(c["id"])

    safe_ids = {path_safe_id(c["id"]) for c in cases}
    for k in ("train_ids", "val_ids", "test_ids"):
        if st.get(k) is not None and not isinstance(st.get(k), list):
            eprint(f"_state.json {k} must be a list of ids")
            sys.exit(2)

    all_split_ids = [
        *(st.get("train_ids") or []),
        *(st.get("val_ids") or []),
        *(st.get("test_ids") or []),
    ]
    for sid in all_split_ids:
        s = str(sid)
        if s in safe_ids:
            continue
        if s != path_safe_id(s):
            eprint(f"_state.json split id '{s}' is not a path-safe id - record split ids exactly as they appear in results.jsonl's prompt_id")
            sys.exit(2)
        eprint(f"note: split id '{s}' matches no loaded case (expected for a trimmed subset run)")

    ref_dir = os.path.join(args["flow"], "baseline", "ref")
    tasks: List[Dict[str, Any]] = []
    for c in cases:
        for rep in range(args["reps"]):
            if f"{path_safe_id(c['id'])}\0{rep}" in done:
                continue
            tasks.append({"c": c, "rep": rep})

    eprint(f"[{args['variant']}] {len(tasks)} of {len(cases) * args['reps']} (id,rep) to run")

    idx = 0
    ok_count = 0
    fail_count = 0
    errors_path = os.path.join(vdir, "errors.jsonl")
    for p in (results_path, errors_path):
        tail = read_if_present(p)
        if tail and not tail.endswith("\n"):
            append_file_no_follow(p, "\n")

    async def worker() -> None:
        nonlocal idx, ok_count, fail_count
        while idx < len(tasks):
            item = tasks[idx]
            idx += 1
            c = item["c"]
            rep = item["rep"]
            safe_id = path_safe_id(c["id"])
            t0 = time.time()
            last_run: Optional[Dict[str, Any]] = None
            row_written = False
            deadline = t0 + args["timeoutS"] if args["timeoutS"] > 0 else float("inf")
            app_retry = {"count": 0}
            judge_retry = {"count": 0}
            try:
                async def run_and_grade():
                    nonlocal last_run
                    t_attempt = t0
                    async def attempt_app():
                        nonlocal t_attempt
                        t_attempt = time.time()
                        return await run_case(c, ctx)

                    run = await with_backoff(attempt_app, app_retry, deadline)
                    last_run = run
                    latency_s = round(time.time() - t_attempt, 4)
                    check_served_model(ctx.get("model"), run.get("model"))

                    ref: Optional[str] = None
                    if args["variant"] != "baseline":
                        base_ref_path = os.path.join(ref_dir, safe_id)
                        for ext in REF_EXTS:
                            try:
                                ref = read_file_no_follow(base_ref_path + ext)
                                break
                            except OSError as err:
                                if err.errno != errno.ENOENT:
                                    raise

                    g = await with_backoff(lambda: grade_case(c, run, ref, ctx), judge_retry, deadline)
                    return run, g, latency_s

                run, g, latency_s = await with_timeout(
                    run_and_grade(), args["timeoutS"], f"{c['id']} rep{rep}"
                )

                meta = dict(c.get("meta") or {})
                if safe_id != str(c["id"]):
                    meta["original_id"] = str(c["id"])
                if app_retry["count"]:
                    meta["retries"] = app_retry["count"]
                if judge_retry["count"]:
                    meta["judge_retries"] = judge_retry["count"]

                stop_reason = run.get("stop_reason")
                is_truncated = stop_reason in ("max_tokens", "MAX_TOKENS", "length")
                status = run.get("status") or ("truncated" if is_truncated else "ok")

                row: Dict[str, Any] = {
                    "prompt_id": safe_id,
                    "rep": rep,
                    "prompt": c.get("prompt") or c.get("input") or c["id"],
                    "tags": c.get("tags"),
                    "attachments": c.get("attachments"),
                    "meta": meta if meta else c.get("meta"),
                    "model": run.get("model"),
                    "usage": run.get("usage"),
                    "stop_reason": stop_reason,
                    "status": status,
                    "judge_model": g.get("judge_model") or run.get("judge_model"),
                    "judge_usage": g.get("judge_usage") or run.get("judge_usage"),
                    "latency_s": latency_s,
                    **perf_from(run),
                    "grade": g.get("grade"),
                    "explanation": g.get("explanation"),
                }
                row_clean = {k: v for k, v in row.items() if v is not None}
                append_file_no_follow(results_path, json.dumps(row_clean, separators=(",", ":")) + "\n")
                row_written = True

                if run.get("transcript") is not None:
                    write_file_no_follow(
                        os.path.join(vdir, "traces", f"{safe_id}_rep{rep}.json"),
                        json.dumps(run["transcript"], indent=2) + "\n",
                    )

                if (
                    args["variant"] == "baseline"
                    and run.get("output") is not None
                    and not any(lexists(os.path.join(ref_dir, safe_id) + ext) for ext in REF_EXTS)
                ):
                    mkdir_no_follow(ref_dir)
                    out_val = run["output"]
                    write_file_no_follow(
                        os.path.join(ref_dir, safe_id),
                        out_val if isinstance(out_val, str) else json.dumps(out_val),
                    )
                ok_count += 1
            except Exception as e:
                fail_count += 1
                if row_written:
                    eprint(f"  [{args['variant']}] {c['id']} rep{rep} scored, but a post-row write failed: {e}")
                    continue
                err_row: Dict[str, Any] = {
                    "prompt_id": safe_id,
                    "rep": rep,
                    **({"original_id": str(c["id"])} if safe_id != str(c["id"]) else {}),
                    "failure_class": getattr(e, "failure_class", "error"),
                    "error": str(e),
                    "retries": app_retry["count"],
                    "judge_retries": judge_retry["count"],
                    "model": last_run.get("model") if last_run else None,
                    "usage": last_run.get("usage") if last_run else None,
                    "judge_model": getattr(e, "judge_model", None) or (last_run.get("judge_model") if last_run else None),
                    "judge_usage": getattr(e, "judge_usage", None) or (last_run.get("judge_usage") if last_run else None),
                    "latency_s": round(time.time() - t0, 4),
                }
                err_clean = {k: v for k, v in err_row.items() if v is not None}
                append_file_no_follow(errors_path, json.dumps(err_clean, separators=(",", ":")) + "\n")
                eprint(f"  [{args['variant']}] {c['id']} rep{rep} FAILED: {e}")

    t_start = time.time()
    def progress() -> None:
        done_now = ok_count + fail_count
        total = len(tasks)
        el = time.time() - t_start
        eta = round((el / done_now) * (total - done_now)) if done_now else None
        line = (
            f"[{args['variant']}] {done_now}/{total} done ({ok_count} ok, {fail_count} failed), "
            f"{round(el)}s elapsed" + (f", ~{eta}s left" if eta is not None else "")
        )
        eprint(line)
        try:
            write_file_no_follow(os.path.join(vdir, "progress.txt"), line + "\n")
        except Exception:
            pass

    async def ticker() -> None:
        while True:
            await asyncio.sleep(30)
            progress()

    WORKERS_STARTED = True
    tick_task = asyncio.create_task(ticker())
    try:
        await asyncio.gather(*(worker() for _ in range(max(1, args["concurrency"]))))
    finally:
        tick_task.cancel()
    progress()
    eprint(f"[{args['variant']}] done - {ok_count} ok, {fail_count} failed -> {results_path}")
    sys.exit(1 if fail_count else 0)

if __name__ == "__main__":
    try:
        asyncio.run(async_main())
    except SystemExit:
        raise
    except Exception as exc:
        msg = str(exc)
        if WORKERS_STARTED:
            eprint("stopped mid-run (rows already written are kept; re-run to resume): " + msg)
            sys.exit(1)
        eprint(msg if msg.startswith("refusing to ") else "refusing to run: " + msg)
        sys.exit(2)
