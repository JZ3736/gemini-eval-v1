#!/usr/bin/env python3
# Adapted from ../report/runner-scaffold.py for a Gemini Model Migration Evaluation
# using Google Cloud Vertex AI (or Google GenAI API) Gemini endpoints.
#
# Usage (Live Vertex AI Gemini):
#   export VERTEX_PROJECT_ID="your-gcp-project-id"
#   export VERTEX_REGION="us-central1"   # or "global"
#   python3 run-eval.py --flow flow --variant baseline --model gemini-2.5-flash --approve-harness
#   python3 run-eval.py --flow flow --variant v1       --model gemini-3.8-flash
#   python3 run-eval.py --flow flow --variant v2       --model gemini-3.8-flash
#
# Usage (Instant local simulation to explore the framework before calling Vertex AI):
#   SIMULATE=1 python3 run-eval.py --flow flow --variant baseline --model gemini-2.5-flash --approve-harness
#   SIMULATE=1 python3 run-eval.py --flow flow --variant v1       --model gemini-3.8-flash
#   SIMULATE=1 python3 run-eval.py --flow flow --variant v2       --model gemini-3.8-flash

import asyncio
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

WIN = sys.platform == 'win32'
NOFOLLOW = 0 if WIN else getattr(os, 'O_NOFOLLOW', 0)


def lstat_or_null(p: str) -> Optional[os.stat_result]:
    try:
        return os.lstat(p)
    except FileNotFoundError:
        return None


def is_symlink(p: str) -> bool:
    st = lstat_or_null(p)
    return os.path.samestat(st, st) and os.path.islink(p) if st is not None else False


ESC_SEQ = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?|\x1b[@-_]')
CONTROL = re.compile(r'[\x00-\x1f\x7f-\x9f]')


def term_safe(s: Any) -> str:
    return CONTROL.sub('', ESC_SEQ.sub('', str(s)))


def eprint(*args: Any) -> None:
    print(*(term_safe(a) for a in args), file=sys.stderr, flush=True)


flow_real_root: Optional[str] = None


def assert_in_flow(dir_path: str, what: str) -> None:
    if flow_real_root is None:
        raise RuntimeError(f"refusing to {what}: flow root not resolved yet")
    dir_real = os.path.realpath(dir_path)
    sep = '\\' if WIN else '/'
    if dir_real != flow_real_root and not dir_real.startswith(flow_real_root + sep):
        raise RuntimeError(f"refusing to {what}: {dir_path} resolves outside the flow directory")


def open_no_follow(p: str, flags: int) -> int:
    parent = os.path.dirname(p) or '.'
    if is_symlink(parent):
        raise RuntimeError(f"refusing to open through symlinked directory: {parent}")
    assert_in_flow(parent, 'open')
    if WIN and is_symlink(p):
        raise RuntimeError(f"refusing to open through symlink: {p}")
    fd = os.open(p, flags | NOFOLLOW, 0o644)
    try:
        st = os.fstat(fd)
        import stat
        if not stat.S_ISREG(st.st_mode):
            raise RuntimeError(f"refusing to use non-regular file: {p}")
        if st.st_nlink > 1:
            raise RuntimeError(f"refusing to use {p}: it has a second hard link")
    except Exception:
        os.close(fd)
        raise
    return fd


def write_file_no_follow(p: str, data: str) -> None:
    fd = open_no_follow(p, os.O_WRONLY | os.O_CREAT)
    try:
        os.ftruncate(fd, 0)
        buf = data.encode('utf-8')
        off = 0
        while off < len(buf):
            n = os.write(fd, buf[off:])
            if n <= 0:
                raise RuntimeError(f"write to {p} made no progress")
            off += n
    finally:
        os.close(fd)


def append_file_no_follow(p: str, data: str) -> None:
    fd = open_no_follow(p, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    try:
        buf = data.encode('utf-8')
        off = 0
        while off < len(buf):
            n = os.write(fd, buf[off:])
            if n <= 0:
                raise RuntimeError(f"append to {p} made no progress")
            off += n
    finally:
        os.close(fd)


def lexists(p: str) -> bool:
    return lstat_or_null(p) is not None


def read_file_no_follow(p: str) -> str:
    fd = open_no_follow(p, os.O_RDONLY)
    try:
        chunks: List[bytes] = []
        while True:
            b = os.read(fd, 65536)
            if not b:
                break
            chunks.append(b)
        return b''.join(chunks).decode('utf-8')
    finally:
        os.close(fd)


def read_if_present(p: str) -> Optional[str]:
    try:
        return read_file_no_follow(p)
    except FileNotFoundError:
        return None


def mkdir_no_follow(dir_path: str) -> None:
    if is_symlink(dir_path):
        raise RuntimeError(f"refusing to use symlinked directory: {dir_path}")
    os.makedirs(dir_path, exist_ok=True)
    assert_in_flow(dir_path, 'create directory')


REF_EXTS = ['', '.html', '.txt', '.json']


# --- Vertex AI Gemini Helper ------------------------------------------------

_cached_access_token: Optional[str] = None


def get_gcp_access_token() -> str:
    global _cached_access_token
    if os.environ.get('VERTEX_ACCESS_TOKEN'):
        return os.environ['VERTEX_ACCESS_TOKEN']
    if not _cached_access_token:
        _cached_access_token = subprocess.check_output(
            ['gcloud', 'auth', 'print-access-token'], encoding='utf-8'
        ).strip()
    return _cached_access_token


def _sync_call_vertex_gemini(model: str, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    project_id = os.environ.get('VERTEX_PROJECT_ID') or os.environ.get('GOOGLE_CLOUD_PROJECT')
    region = os.environ.get('VERTEX_REGION') or os.environ.get('GOOGLE_CLOUD_LOCATION') or 'us-central1'

    if not project_id:
        raise RuntimeError(
            'Missing VERTEX_PROJECT_ID (or GOOGLE_CLOUD_PROJECT). Set it to your GCP project ID, '
            'or run with SIMULATE=1 for an offline run.'
        )

    host = (
        'https://aiplatform.googleapis.com'
        if region == 'global'
        else f'https://{region}-aiplatform.googleapis.com'
    )
    url = f'{host}/v1/projects/{project_id}/locations/{region}/publishers/google/models/{model}:generateContent'

    token = get_gcp_access_token()
    payload = {
        'systemInstruction': {'parts': [{'text': system_prompt}]},
        'contents': [{'role': 'user', 'parts': [{'text': user_prompt}]}],
        'generationConfig': {
            'temperature': 0.0,
            'maxOutputTokens': 512,
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        err_text = e.read().decode('utf-8', errors='replace')
        err = RuntimeError(f'Vertex AI HTTP {e.code}: {err_text}')
        setattr(err, 'status', e.code)
        raise err


async def call_vertex_gemini(model: str, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    return await asyncio.to_thread(_sync_call_vertex_gemini, model, system_prompt, user_prompt)


def simulate_vertex_gemini(variant: str, model: str, input_case: Dict[str, Any]) -> Dict[str, Any]:
    exp = input_case['expected']
    obj = {
        'category': exp['category'],
        'priority': exp['priority'],
        'requires_escalation': exp['requires_escalation'],
        'summary': f"Triaged {input_case['id']} ({exp['category']}).",
    }

    # Simulate realistic Gemini model migration behavior:
    # 1) baseline (older model: gemini-2.5-flash):
    #    Gets fooled by angry/urgent phrasing ("emotional_trap") and misses subtle degradation
    tags = input_case.get('tags') or []
    if variant == 'baseline':
        if 'emotional_trap' in tags:
            obj['requires_escalation'] = True  # False positive escalation!
            obj['priority'] = 'p0'
        if 'subtle' in tags:
            obj['requires_escalation'] = False  # False negative on subtle outage!

    text = json.dumps(obj, indent=2)

    # 2) v1 (migrated to newer model gemini-3.8-flash or gemini-4-pro with UNCHANGED prompt):
    #    Reasoning is much better (gets all classifications & escalations right),
    #    but wraps JSON output in ```json ... ``` markdown fences unless told not to
    #    (or unless response_mime_type="application/json" is set)!
    if variant == 'v1':
        text = '```json\n' + text + '\n```'

    # 3) v2 (newer model gemini-3.8-flash / gemini-4-pro + updated prompt in prompts.json):
    #    Both reasoning AND raw JSON formatting pass 100%.

    served_model = f"{model or 'gemini-2.5-flash'}-001"
    thinking_tokens = 0 if variant == 'baseline' else 92
    return {
        'modelVersion': served_model,
        'candidates': [
            {
                'finishReason': 'STOP',
                'content': {
                    'role': 'model',
                    'parts': (
                        [{'thought': True, 'text': f"Evaluating escalation criteria for {input_case['id']}."}]
                        if thinking_tokens > 0
                        else []
                    ) + [{'text': text}],
                },
            }
        ],
        'usageMetadata': {
            'promptTokenCount': 160,
            'candidatesTokenCount': 56,
            'thoughtsTokenCount': thinking_tokens,
            'cachedContentTokenCount': 0,
        },
    }


# --- Fill in the 3 functions required by runner-scaffold.py -----------------

async def load_cases() -> List[Dict[str, Any]]:
    """1. Return the list of input cases. Each must have a stable `id`."""
    with open('cases.json', 'r', encoding='utf-8') as f:
        return json.load(f)


async def run_case(input_case: Dict[str, Any], ctx: Dict[str, Any]) -> Dict[str, Any]:
    """2. Run the app on one input against Vertex AI Gemini (or SIMULATE=1)."""
    with open('prompts.json', 'r', encoding='utf-8') as f:
        prompts = json.load(f)
    variant = ctx['variant']
    system_prompt = prompts.get(variant) or prompts['baseline']
    requested_model = ctx.get('model') or ('gemini-2.5-flash' if variant == 'baseline' else 'gemini-3.8-flash')

    if os.environ.get('SIMULATE') == '1':
        res = simulate_vertex_gemini(variant, requested_model, input_case)
    else:
        res = await call_vertex_gemini(requested_model, system_prompt, input_case['prompt'])

    cand = (res.get('candidates') or [{}])[0]
    parts = (cand.get('content') or {}).get('parts') or []
    thought_texts = [p.get('text', '') for p in parts if p.get('thought')]
    output_texts = [p.get('text', '') for p in parts if not p.get('thought') and 'text' in p]
    output_text = '\n'.join(output_texts).strip()
    thinking_text = '\n'.join(thought_texts).strip() or None

    um = res.get('usageMetadata') or {}
    usage = {
        'input_tokens': um.get('promptTokenCount', 0),
        'output_tokens': um.get('candidatesTokenCount', 0),
        'thinking_tokens': um.get('thoughtsTokenCount', 0),
        'cache_read_input_tokens': um.get('cachedContentTokenCount', 0),
    }

    assistant_turn: Dict[str, Any] = {'role': 'assistant', 'content': output_text}
    if thinking_text:
        assistant_turn['thinking'] = thinking_text

    return {
        'output': output_text,
        'transcript': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': input_case['prompt']},
            assistant_turn,
        ],
        'model': res.get('modelVersion') or requested_model,
        'usage': usage,
        'stop_reason': cand.get('finishReason', 'STOP'),
    }


async def grade_case(
    input_case: Dict[str, Any],
    run: Dict[str, Any],
    _ref: Optional[str],
    _ctx: Dict[str, Any],
) -> Dict[str, Any]:
    """3. Grade one output programmatically against expected fields and formatting rules."""
    raw = str(run.get('output') or '').strip()
    has_markdown_fence = bool(re.match(r'^```', raw))
    no_markdown_fence = 0 if has_markdown_fence else 1

    # Strip optional markdown fence so we can still measure semantic accuracy separately
    cleaned = re.sub(r'\s*```$', '', re.sub(r'^```(?:json)?\s*', '', raw, flags=re.IGNORECASE)).strip()
    parsed = None
    try:
        parsed = json.loads(cleaned)
    except Exception:
        parsed = None

    exp = input_case['expected']
    category_match = 1 if (isinstance(parsed, dict) and parsed.get('category') == exp['category']) else 0
    escalation_match = 1 if (isinstance(parsed, dict) and parsed.get('requires_escalation') == exp['requires_escalation']) else 0
    passed = 1 if (no_markdown_fence == 1 and category_match == 1 and escalation_match == 1) else 0

    failures: List[str] = []
    if not no_markdown_fence:
        failures.append('wrapped in markdown fence')
    if not category_match:
        got_cat = parsed.get('category') if isinstance(parsed, dict) else None
        failures.append(f"category={got_cat} (expected {exp['category']})")
    if not escalation_match:
        got_esc = parsed.get('requires_escalation') if isinstance(parsed, dict) else None
        failures.append(f"requires_escalation={got_esc} (expected {exp['requires_escalation']})")

    return {
        'grade': {
            'pass': passed,
            'category_match': category_match,
            'escalation_match': escalation_match,
            'no_markdown_fence': no_markdown_fence,
        },
        'explanation': {
            'pass': (
                'Valid raw JSON with exact category and escalation match.'
                if passed
                else f"Failed checks: {'; '.join(failures)}"
            ),
        },
    }


def perf_from(run: Dict[str, Any]) -> Dict[str, Any]:
    """Side-channel perf fields surfaced in the report."""
    usage = run.get('usage') or {}
    return {
        'in_tokens': usage.get('input_tokens', 0),
        'out_tokens': usage.get('output_tokens', 0),
        'thinking_tokens': usage.get('thinking_tokens', 0),
    }


# --- harness (from ../report/runner-scaffold.py) ----------------------------

def usage_msg() -> None:
    eprint(
        'usage: python3 run-eval.py --flow DIR --variant ID '
        '[--model ID] [--reps N] [--concurrency N] [--timeout-s N (0 = no ceiling)] [--approve-harness]'
    )


def parse_args(argv: List[str]) -> Dict[str, Any]:
    a: Dict[str, Any] = {
        'flow': '.antigravity/hillclimb/flow',
        'variant': 'baseline',
        'model': None,
        'reps': 1,
        'concurrency': 4,
        'timeout_s': 1800.0,
        'approve_harness': False,
    }
    i = 0

    def val(idx: int) -> str:
        if idx >= len(argv):
            eprint(f"missing value for {argv[idx - 1]}")
            usage_msg()
            sys.exit(2)
        return argv[idx]

    while i < len(argv):
        k = argv[i]
        if k == '--flow':
            i += 1
            a['flow'] = val(i)
        elif k == '--variant':
            i += 1
            a['variant'] = val(i)
        elif k == '--model':
            i += 1
            a['model'] = val(i)
        elif k == '--reps':
            i += 1
            try:
                a['reps'] = int(val(i))
            except ValueError:
                usage_msg()
                sys.exit(2)
        elif k == '--concurrency':
            i += 1
            try:
                a['concurrency'] = int(val(i))
            except ValueError:
                usage_msg()
                sys.exit(2)
        elif k == '--timeout-s':
            i += 1
            try:
                a['timeout_s'] = float(val(i))
            except ValueError:
                usage_msg()
                sys.exit(2)
        elif k == '--approve-harness':
            a['approve_harness'] = True
        elif k in ('-h', '--help'):
            usage_msg()
            sys.exit(0)
        else:
            eprint(f"unknown argument: {k}")
            usage_msg()
            sys.exit(2)
        i += 1

    if not re.match(r'^(baseline|v[1-9]\d*)$', str(a['variant'])):
        eprint(f"--variant must be 'baseline' or 'v<N>', got '{a['variant']}'")
        usage_msg()
        sys.exit(2)

    if (
        a['timeout_s'] < 0
        or a['timeout_s'] * 1000 > 2147483647
        or a['reps'] < 1
        or a['concurrency'] < 1
    ):
        usage_msg()
        sys.exit(2)
    return a


LOCKFILE_NAMES = [
    'uv.lock',
    'poetry.lock',
    'Pipfile.lock',
    'requirements.txt',
    'pyproject.toml',
    'package-lock.json',
    'bun.lock',
    'bun.lockb',
    'yarn.lock',
    'pnpm-lock.yaml',
]


def check_harness(state_path: str, st: Dict[str, Any], approve: bool) -> None:
    self_path = os.path.abspath(__file__)
    raw_listed = st.get('harness_paths')
    listed = [str(x) for x in raw_listed] if isinstance(raw_listed, list) else []
    search_dirs = list(dict.fromkeys([os.path.dirname(self_path), os.getcwd()]))
    lockfiles: List[str] = []
    for d in search_dirs:
        for fn in LOCKFILE_NAMES:
            cand = os.path.join(d, fn)
            if os.path.exists(cand) and cand not in lockfiles:
                lockfiles.append(cand)
    all_paths = sorted(set([self_path] + lockfiles + [os.path.abspath(p) for p in listed]))
    h = hashlib.sha256()
    hashed: List[str] = []
    cwd = os.getcwd()
    for p in all_paths:
        try:
            with open(p, 'rb') as f:
                buf = f.read()
        except Exception as e:
            if p == self_path:
                raise
            rel = os.path.relpath(p, cwd)
            eprint(f"warning: harness path '{rel}' not readable ({getattr(e, 'strerror', 'error')}) - skipped")
            continue
        rel = os.path.relpath(p, cwd)
        h.update(rel.encode('utf-8'))
        h.update(b'\0')
        h.update(buf)
        h.update(b'\0')
        hashed.append(rel)
    sha = h.hexdigest()
    if st.get('harness_sha') == sha:
        return
    if not lockfiles:
        eprint('note: no lockfile beside the runner or in the current directory - dependency changes are outside the harness sha')
    if approve:
        st['harness_sha'] = sha
        write_file_no_follow(state_path, json.dumps(st, indent=2) + '\n')
        eprint(f"harness approved: sha256 {sha[:12]} over {len(hashed)} file(s) recorded in {state_path}")
        return
    if st.get('harness_sha') is None:
        eprint(f"no approved harness sha in {state_path} (computed {sha[:12]} over: {', '.join(hashed)}).")
        eprint('Review the harness, then run once with --approve-harness to record it.')
    else:
        eprint(
            f"harness changed since last approved run (files: {', '.join(hashed)}); "
            f"approved {str(st.get('harness_sha'))[:12]}, now {sha[:12]}."
        )
        eprint('Re-run with --approve-harness after reviewing the diff.')
    sys.exit(2)


async def with_backoff(
    fn: Callable[[], Any],
    retry: Dict[str, int],
    deadline: float = float('inf'),
    tries: int = 5,
) -> Any:
    attempt = 0
    while True:
        if time.monotonic() >= deadline:
            e = RuntimeError('wall-clock ceiling exceeded before attempt')
            setattr(e, 'failure_class', 'timeout')
            raise e
        try:
            return await fn()
        except Exception as e:
            status = getattr(e, 'status', None) or getattr(e, 'code', None) or getattr(getattr(e, 'response', None), 'status_code', None)
            msg = str(e)
            transient = (
                status in (429, 529)
                or (isinstance(status, int) and 500 <= status < 600)
                or bool(re.search(r'overloaded|rate.?limit|resource.?exhausted|quota|unavailable', msg, re.IGNORECASE))
            )
            if not transient or attempt >= tries - 1:
                raise
            delay_s = min(60.0, (2 ** attempt)) * (0.5 + random.random())
            if time.monotonic() + delay_s >= deadline:
                raise
            retry['count'] += 1
            await asyncio.sleep(delay_s)
            attempt += 1


async def with_timeout(coro: Any, seconds: float, label: str) -> Any:
    if not (seconds > 0):
        return await coro
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except asyncio.TimeoutError:
        e = RuntimeError(f"{label}: exceeded {seconds:g}s wall-clock ceiling")
        setattr(e, 'failure_class', 'timeout')
        raise e


def path_safe_id(raw_id: Any) -> str:
    raw = str(raw_id)
    cleaned = re.sub(r'[^\w.-]', '_', raw)
    if cleaned == raw and len(raw) <= 129:
        return raw
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()[:8]
    return f"{cleaned[:120]}-{digest}"


def normalize_model_base(model_id: str) -> str:
    s = str(model_id).strip()
    if '/' in s:
        s = s.split('/')[-1]
    s = re.sub(r'[-@](\d{8}|\d{4}-\d{2}-\d{2}|\d{3})$|-latest$|-0$|-preview(?:-[\w.-]+)?$|-exp(?:-[\w.-]+)?$', '', s)
    return s


def served_model_matches(requested: str, served: str) -> bool:
    if requested == served:
        return True
    req_base = normalize_model_base(requested)
    srv_base = normalize_model_base(served)
    return bool(req_base and req_base == srv_base)


def is_truncated_stop(stop_reason: Any) -> bool:
    if not stop_reason:
        return False
    s = str(stop_reason).strip().lower()
    return s in ('max_tokens', 'length', 'FinishReason.MAX_TOKENS'.lower()) or s.endswith('max_tokens')


workers_started = False


async def async_main() -> None:
    global flow_real_root, workers_started
    args = parse_args(sys.argv[1:])
    if WIN:
        args['flow'] = re.sub(r'(.)[\\/]+$', r'\1', args['flow'])
        flow_segments = re.split(r'[\\/]', args['flow'])
    else:
        args['flow'] = re.sub(r'(.)/+$', r'\1', args['flow'])
        flow_segments = args['flow'].split('/')

    if any(seg in ('.', '..') for seg in flow_segments):
        eprint(f"refusing to run: --flow must not contain '.' or '..' segments, got '{args['flow']}'")
        sys.exit(2)

    vdir = os.path.join(args['flow'], args['variant'])
    check_paths = [
        args['flow'],
        os.path.join(args['flow'], 'baseline'),
        vdir,
        os.path.join(vdir, 'traces'),
        os.path.join(vdir, 'results.jsonl'),
        os.path.join(vdir, 'errors.jsonl'),
        os.path.join(vdir, 'progress.txt'),
        os.path.join(args['flow'], 'baseline', 'ref'),
        os.path.join(args['flow'], '_state.json'),
    ]
    for p in check_paths:
        if is_symlink(p):
            eprint(f"refusing to run: {p} is a symlink (the flow dir must hold regular files)")
            sys.exit(2)

    if not os.path.isabs(args['flow']):
        walk = ''
        non_empty = [seg for seg in flow_segments if seg][:-1]
        for part in non_empty:
            walk = os.path.join(walk, part) if walk else part
            if is_symlink(walk):
                eprint(f"refusing to run: {walk} is a symlink (ancestor of --flow)")
                sys.exit(2)

    os.makedirs(args['flow'], exist_ok=True)
    flow_real_root = os.path.realpath(args['flow'])
    mkdir_no_follow(os.path.join(vdir, 'traces'))

    state_path = os.path.join(args['flow'], '_state.json')
    st: Dict[str, Any] = {}
    state_text = read_if_present(state_path)
    if state_text is not None:
        try:
            parsed = json.loads(state_text)
            st = parsed if isinstance(parsed, dict) else {}
        except Exception:
            eprint(f"{state_path} exists but is not valid JSON - fix it before spending a pass")
            sys.exit(2)

    check_harness(state_path, st, args['approve_harness'])
    ctx = {**args, 'state': st}

    results_path = os.path.join(vdir, 'results.jsonl')
    done = set()
    existing_results = read_if_present(results_path) or ''
    for ln in existing_results.split('\n'):
        if not ln.strip():
            continue
        try:
            r = json.loads(ln)
            done.add(f"{r.get('prompt_id')}\0{r.get('rep')}")
        except Exception:
            pass

    cases = await load_cases()
    seen: Dict[str, Any] = {}
    for c in cases:
        k = path_safe_id(c['id']).lower()
        if k in seen:
            eprint(f"duplicate case id after sanitization: '{c['id']}' collides with '{seen[k]}'")
            sys.exit(2)
        seen[k] = c['id']

    safe_ids = {path_safe_id(c['id']) for c in cases}
    for k in ('train_ids', 'val_ids', 'test_ids'):
        if st.get(k) is not None and not isinstance(st.get(k), list):
            eprint(f"_state.json {k} must be a list of ids")
            sys.exit(2)

    split_ids = (st.get('train_ids') or []) + (st.get('val_ids') or []) + (st.get('test_ids') or [])
    for sid in split_ids:
        s = str(sid)
        if s in safe_ids:
            continue
        if s != path_safe_id(s):
            eprint(f"_state.json split id '{s}' is not a path-safe id - record split ids exactly as they appear in results.jsonl's prompt_id")
            sys.exit(2)
        eprint(f"note: split id '{s}' matches no loaded case (expected for a trimmed subset run)")

    ref_dir = os.path.join(args['flow'], 'baseline', 'ref')
    tasks: List[Tuple[Dict[str, Any], int]] = []
    for c in cases:
        for rep in range(args['reps']):
            if f"{path_safe_id(c['id'])}\0{rep}" in done:
                continue
            tasks.append((c, rep))

    eprint(f"[{args['variant']}] {len(tasks)} of {len(cases) * args['reps']} (id,rep) to run")

    idx = 0
    ok = 0
    fail = 0
    errors_path = os.path.join(vdir, 'errors.jsonl')
    for p in (results_path, errors_path):
        tail = read_if_present(p)
        if tail and not tail.endswith('\n'):
            append_file_no_follow(p, '\n')

    async def worker() -> None:
        nonlocal idx, ok, fail
        while idx < len(tasks):
            c, rep = tasks[idx]
            idx += 1
            safe_id = path_safe_id(c['id'])
            t0_wall = time.monotonic()
            last_run: Optional[Dict[str, Any]] = None
            row_written = False
            deadline = t0_wall + args['timeout_s'] if args['timeout_s'] > 0 else float('inf')
            app_retry = {'count': 0}
            judge_retry = {'count': 0}
            try:
                async def run_and_grade() -> Tuple[Dict[str, Any], Dict[str, Any], float]:
                    nonlocal last_run
                    t_attempt = t0_wall

                    async def _do_run() -> Dict[str, Any]:
                        nonlocal t_attempt
                        t_attempt = time.monotonic()
                        return await run_case(c, ctx)

                    run = await with_backoff(_do_run, app_retry, deadline)
                    last_run = run
                    latency_s = time.monotonic() - t_attempt
                    if ctx.get('model') and run.get('model') and not served_model_matches(ctx['model'], run['model']):
                        err = RuntimeError(f"served model {run.get('model')} != requested {ctx.get('model')}")
                        setattr(err, 'failure_class', 'serving_substitution')
                        raise err

                    ref: Optional[str] = None
                    if args['variant'] != 'baseline':
                        p_base = os.path.join(ref_dir, safe_id)
                        for ext in REF_EXTS:
                            try:
                                ref = read_file_no_follow(p_base + ext)
                                break
                            except FileNotFoundError:
                                continue

                    async def _do_grade() -> Dict[str, Any]:
                        return await grade_case(c, run, ref, ctx)

                    g = await with_backoff(_do_grade, judge_retry, deadline)
                    return run, g, latency_s

                run, g, latency_s = await with_timeout(run_and_grade(), args['timeout_s'], f"{c['id']} rep{rep}")

                meta = dict(c.get('meta') or {}) if c.get('meta') else {}
                if safe_id != str(c['id']):
                    meta['original_id'] = str(c['id'])
                if app_retry['count']:
                    meta['retries'] = app_retry['count']
                if judge_retry['count']:
                    meta['judge_retries'] = judge_retry['count']

                row: Dict[str, Any] = {
                    'prompt_id': safe_id,
                    'rep': rep,
                    'prompt': c.get('prompt') if c.get('prompt') is not None else (c.get('input') if c.get('input') is not None else c['id']),
                }
                if c.get('tags') is not None:
                    row['tags'] = c['tags']
                if c.get('attachments') is not None:
                    row['attachments'] = c['attachments']
                if meta:
                    row['meta'] = meta
                row['model'] = run.get('model')
                row['usage'] = run.get('usage')
                row['stop_reason'] = run.get('stop_reason')
                row['status'] = run.get('status') or ('truncated' if is_truncated_stop(run.get('stop_reason')) else 'ok')
                judge_model = g.get('judge_model') or run.get('judge_model')
                judge_usage = g.get('judge_usage') or run.get('judge_usage')
                if judge_model is not None:
                    row['judge_model'] = judge_model
                if judge_usage is not None:
                    row['judge_usage'] = judge_usage
                row['latency_s'] = round(latency_s, 4)
                row.update(perf_from(run))
                row['grade'] = g.get('grade')
                if g.get('explanation') is not None:
                    row['explanation'] = g['explanation']

                append_file_no_follow(results_path, json.dumps(row) + '\n')
                row_written = True
                if run.get('transcript') is not None:
                    write_file_no_follow(
                        os.path.join(vdir, 'traces', f"{safe_id}_rep{rep}.json"),
                        json.dumps(run['transcript'], indent=2),
                    )
                if (
                    args['variant'] == 'baseline'
                    and run.get('output') is not None
                    and not any(lexists(os.path.join(ref_dir, safe_id) + ext) for ext in REF_EXTS)
                ):
                    mkdir_no_follow(ref_dir)
                    out_val = run['output'] if isinstance(run['output'], str) else json.dumps(run['output'])
                    write_file_no_follow(os.path.join(ref_dir, safe_id), out_val)
                ok += 1
            except Exception as e:
                fail += 1
                if row_written:
                    eprint(f"  [{args['variant']}] {c['id']} rep{rep} scored, but a post-row write failed: {e}")
                    continue
                err_row: Dict[str, Any] = {
                    'prompt_id': safe_id,
                    'rep': rep,
                }
                if safe_id != str(c['id']):
                    err_row['original_id'] = str(c['id'])
                err_row['failure_class'] = getattr(e, 'failure_class', 'error')
                err_row['error'] = str(e)
                err_row['retries'] = app_retry['count']
                err_row['judge_retries'] = judge_retry['count']
                if last_run and last_run.get('model') is not None:
                    err_row['model'] = last_run.get('model')
                if last_run and last_run.get('usage') is not None:
                    err_row['usage'] = last_run.get('usage')
                jm = getattr(e, 'judge_model', None) or (last_run.get('judge_model') if last_run else None)
                ju = getattr(e, 'judge_usage', None) or (last_run.get('judge_usage') if last_run else None)
                if jm is not None:
                    err_row['judge_model'] = jm
                if ju is not None:
                    err_row['judge_usage'] = ju
                err_row['latency_s'] = round(time.monotonic() - t0_wall, 4)
                append_file_no_follow(errors_path, json.dumps(err_row) + '\n')
                eprint(f"  [{args['variant']}] {c['id']} rep{rep} FAILED: {e}")

    t0_batch = time.monotonic()

    def progress() -> None:
        done_cnt = ok + fail
        total_cnt = len(tasks)
        el = time.monotonic() - t0_batch
        eta = round((el / done_cnt) * (total_cnt - done_cnt)) if done_cnt else None
        line = (
            f"[{args['variant']}] {done_cnt}/{total_cnt} done ({ok} ok, {fail} failed), "
            f"{round(el)}s elapsed" + (f", ~{eta}s left" if eta is not None else '')
        )
        eprint(line)
        try:
            write_file_no_follow(os.path.join(vdir, 'progress.txt'), line + '\n')
        except Exception:
            pass

    async def ticker() -> None:
        while True:
            await asyncio.sleep(30.0)
            progress()

    tick_task = asyncio.create_task(ticker())
    workers_started = True
    try:
        await asyncio.gather(*(worker() for _ in range(max(1, args['concurrency']))))
    finally:
        tick_task.cancel()
    progress()
    eprint(f"[{args['variant']}] done - {ok} ok, {fail} failed -> {results_path}")
    sys.exit(1 if fail else 0)


if __name__ == '__main__':
    try:
        asyncio.run(async_main())
    except SystemExit:
        raise
    except Exception as exc:
        msg = str(exc)
        if workers_started:
            eprint('stopped mid-run (rows already written are kept; re-run to resume): ' + msg)
            sys.exit(1)
        eprint(msg if msg.startswith('refusing to ') else 'refusing to run: ' + msg)
        sys.exit(2)
