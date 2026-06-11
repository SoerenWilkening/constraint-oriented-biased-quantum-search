"""M3 LLM-FunSearch proposer (bd 8an.4.7, NORTHSTAR §10).

The second concrete ``proposer`` behind the :func:`benchmarks.m3.evolve` seam
(``proposer(population, rng) -> list[Candidate]``). Where the parametric
proposer (:mod:`benchmarks.m3_proposer`) mutates a *fixed genome vector*, this
one mutates schedule-factory **source code** — NORTHSTAR §10's literal design:
"LLM mutates from high-scoring exemplars + observed anytime curves." It plugs
into the SAME seam and the SAME downstream gate / evaluator; no harness rework.

Why a separate, heavier firewall (the reason bd 8an.4.7 was deferred behind the
parametric proposer): for the genome proposer the §1.4 feature allow-list holds
BY CONSTRUCTION — :func:`benchmarks.m3_proposer.genome_to_factory` can only emit
whitelisted features and legal lever keys. **Generated code can compute
anything.** A factory that derives a per-variable θ from an eigenvector or a
PageRank score (banned §1.4 — uncharged classical optimization) still emits the
*legal* key ``opt_branching_weights``, so the existing resolved-param allow-list
(:func:`benchmarks.candidate_gate.check_param_allowlist`, which only inspects
output KEYS) would wave it through. Nothing inspects what a factory *computes*.
This module is that missing inspector: an **AST/provenance firewall** that
proves, before the code is ever executed, that it computes only allow-listed
features through the closed registry and emits only legal levers.

Faithfulness firewall (CLAUDE.md §1.4 / §1.6 / §2.1), in three layers:

1. **Constrained DSL.** Generated programs are a single function
   ``build_schedule(n, feat, oracle_budget) -> {param: value}``. They never see
   the raw ``c1/c2/c3`` matrices — the only door to per-variable structure is
   ``feat("<name>")``, which resolves through the CLOSED
   :data:`benchmarks.m3_proposer.FEATURES` registry (== EXACTLY the §1.4
   allow-list). There is no code path from generated code to a banned
   (LP/SDP/spectral/iterative) statistic.
2. **Static AST whitelist** (:func:`validate_source`) — deny-by-default node
   types, loadable names, call targets, and emitted dict keys. No imports, no
   loops/comprehensions (the structural defense against power-iteration /
   PageRank / k-core / betweenness), no attribute access, no dunders, no
   ``eval``/``exec``/``open``, no list/tuple literals and no string constants
   outside keys/``feat`` args (closes sequence-replication memory blow-ups).
   ``feat(...)`` takes a string LITERAL that must be in the registry; every
   emitted key must be in :data:`benchmarks.candidate_gate.LEGAL_LEVER_PARAMS`.
3. **Restricted, resource-bounded execution** (:func:`compile_factory` /
   :func:`compile_candidate_factory`) — ``exec`` with an empty ``__builtins__``
   and only the whitelisted helpers injected; then a **subprocess-isolated,
   CPU/memory/wall-clock-bounded smoke test at multiple strata** (n=10/100/1000)
   so a crashing, malformed, or runtime-blow-up factory (a bignum chain that the
   static pass cannot see) is killed and dropped — never handed to the
   multi-hour solve. Every failure surfaces as :class:`FaithfulnessError`
   (fail-loud, §2.1), so one bad generation can never crash the ``evolve`` loop.

A validated candidate is an ordinary :class:`benchmarks.m3.Candidate` and flows
through the unchanged :func:`benchmarks.candidate_gate.admit` (param-allowlist +
scale-invariance) and :func:`benchmarks.m3.evaluate_candidate` — defense in
depth: the firewall catches a banned *computation*, the gate catches a banned
*key* and a scale-drifting *realized lever*.

The LLM client is a pluggable seam (``client(system, user) -> str``) so the loop
is fully testable with a :class:`FakeLLMClient` (no network) and the genome
bridge (:func:`genome_to_source`) seeds exemplars from the parametric population.
:class:`AnthropicLLMClient` is the optional real client — ``anthropic`` is
imported lazily so it is NOT a hard dependency of this benchmark package.

Unlike the parametric proposer, this proposer is **not** bit-for-bit
reproducible: a live LLM is non-deterministic by nature. ``rng`` still drives the
reproducible parts (exemplar choice, prompt nonce); the parametric proposer
remains the reproducible search engine, this one the exploratory idea source.
"""
import ast
import hashlib
import multiprocessing
import queue as _queue
import re

import numpy as np

try:  # POSIX-only; used to hard-cap the smoke subprocess's memory + CPU
    import resource as _resource
except ImportError:  # pragma: no cover - non-POSIX
    _resource = None

try:  # package import (pytest / installed) vs flat script import
    from benchmarks import candidate_gate, m2, m3_proposer, metric
    from benchmarks.m3 import Candidate
except ImportError:  # pragma: no cover - flat layout fallback
    import candidate_gate  # type: ignore
    import m2  # type: ignore
    import m3_proposer  # type: ignore
    import metric  # type: ignore
    from m3 import Candidate  # type: ignore


class FaithfulnessError(ValueError):
    """A generated factory violated the §1.4/§1.6 firewall or is unsafe.

    Raised by :func:`validate_source` / :func:`compile_factory` (fail loud,
    §2.1). The proposer catches it per-candidate (a single bad generation must
    not kill a multi-hour ``evolve`` run) and records the rejection, exactly as
    :func:`benchmarks.candidate_gate.admit` gates a candidate out rather than
    crashing the loop.
    """


# --------------------------------------------------------------------------- #
# The constrained DSL surface
# --------------------------------------------------------------------------- #

#: The one function a generated program must define, and its exact signature.
FACTORY_NAME = "build_schedule"
FACTORY_ARGS = ("n", "feat", "oracle_budget")

#: Allow-listed per-variable feature names a generated ``feat("...")`` may
#: request — EXACTLY the NORTHSTAR §1.4 registry minus the ``"none"`` OFF switch
#: (turning θ off is "don't emit ``opt_branching_weights``", not ``feat("none")``,
#: which returns ``None`` and cannot be scaled). Derived from the SHARED closed
#: registry so it can never drift from the parametric proposer's allow-list.
FEATURE_NAMES = frozenset(
    name for name, _ in m3_proposer.FEATURES if name != "none")

#: Builtins/helpers injected into the sandbox globals and the ONLY non-local
#: names a generated body may load. ``clip`` is the bounded-θ helper (§1.7);
#: ``feat`` / ``oracle_budget`` are passed as arguments (bound, not global).
_SANDBOX_HELPERS = ("clip", "int", "round", "float", "min", "max", "abs", "len")
_WHITELIST_GLOBALS = frozenset(_SANDBOX_HELPERS)
#: Every name that may appear as a Call target: the helpers + the two callable
#: arguments. (Attribute calls are impossible — Attribute nodes are forbidden.)
_ALLOWED_CALLS = _WHITELIST_GLOBALS | {"feat", "oracle_budget"}

#: Source-length and node-count caps — bound parse/validate cost on adversarial
#: input before any structural check runs.
_MAX_SOURCE_CHARS = 20_000
_MAX_AST_NODES = 4_000

#: Resource-bounded smoke test (closes the runtime DoS the static pass cannot
#: see — a loop-free bignum/allocation blow-up). The factory is resolved at
#: these strata (covering the small/compression regime AND the n the §10 gate
#: re-resolves at, ``candidate_gate.admit`` ``scale_ns``) inside a killable
#: subprocess; an overrun of any budget is a :class:`FaithfulnessError`.
SMOKE_STRATA = (10, 100, 1000)
SMOKE_TIMEOUT_S = 12.0          #: wall-clock kill (a legal factory resolves in <<1s)
SMOKE_MEM_MB = 2048             #: best-effort address-space cap (RLIMIT_AS, POSIX)
SMOKE_CPU_S = 12                #: best-effort CPU-seconds backstop (RLIMIT_CPU, POSIX)


def _ast_types(*names):
    """Resolve ast class names that exist on this Python, dropping the rest
    (e.g. ``Index`` is gone on 3.9+; ``Num``/``Str`` legacy aliases vary)."""
    out = []
    for n in names:
        cls = getattr(ast, n, None)
        if cls is not None:
            out.append(cls)
    return tuple(out)


#: Deny-by-default node whitelist. Anything not here is rejected by type alone —
#: notably absent: Import/ImportFrom, For/While/comprehensions, Attribute,
#: Lambda, With/Try, Global/Nonlocal, Starred, Yield/Await, AugAssign, Slice,
#: keyword (kwargs). Their absence is the firewall, so add to this set only with
#: a matching test that the addition cannot reach a banned feature.
#: NOTE: List/Tuple literals are intentionally ABSENT — the DSL never needs them
#: (params is a Dict; feature vectors come from feat()), and allowing them opens
#: a sequence-replication memory DoS (`[0] * k * k * k`). String constants are
#: separately restricted to dict keys / feat() args (see validate_source) so
#: `"x" * k` cannot replicate either.
_ALLOWED_NODES = frozenset(_ast_types(
    "Module", "FunctionDef", "arguments", "arg",
    "Return", "Assign", "Expr", "Pass", "If",
    "BinOp", "UnaryOp", "BoolOp", "Compare", "IfExp", "Call",
    "Dict", "Name", "Constant", "Subscript",
    "Load", "Store", "Index",
    # operators
    "Add", "Sub", "Mult", "Div", "FloorDiv", "Mod",
    "USub", "UAdd", "Not", "And", "Or",
    "Eq", "NotEq", "Lt", "LtE", "Gt", "GtE",
))


# --------------------------------------------------------------------------- #
# Static AST firewall
# --------------------------------------------------------------------------- #

def _is_str_constant(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _subscript_key(node):
    """The literal string key of a ``Subscript`` (``params["x"]``), or None.

    Handles both 3.9+ (``node.slice`` is the expr) and the legacy ``ast.Index``
    wrapper, so a generated ``params["opt_branching_radius"] = ...`` is checked
    against :data:`LEGAL_LEVER_PARAMS` on every Python.
    """
    s = node.slice
    if getattr(ast, "Index", None) is not None and isinstance(s, ast.Index):
        s = s.value  # pragma: no cover - 3.8 only
    return s.value if _is_str_constant(s) else None


def _function_def(tree):
    """The single top-level ``build_schedule`` def, validated, or raise."""
    body = tree.body
    if len(body) != 1 or not isinstance(body[0], ast.FunctionDef):
        raise FaithfulnessError(
            "program must be EXACTLY one top-level function "
            f"`def {FACTORY_NAME}(...)` and nothing else (no module-level "
            "imports, assignments, or extra defs)")
    fn = body[0]
    if fn.name != FACTORY_NAME:
        raise FaithfulnessError(
            f"the function must be named {FACTORY_NAME!r}, got {fn.name!r}")
    a = fn.args
    extras = (a.vararg, a.kwarg, a.defaults, a.kw_defaults, a.kwonlyargs,
              getattr(a, "posonlyargs", []))
    if any(extras):
        raise FaithfulnessError(
            f"{FACTORY_NAME} must take exactly the positional args "
            f"{FACTORY_ARGS} — no *args/**kwargs/defaults/keyword-only")
    got = tuple(arg.arg for arg in a.args)
    if got != FACTORY_ARGS:
        raise FaithfulnessError(
            f"{FACTORY_NAME} signature must be {FACTORY_ARGS}, got {got}")
    return fn


def _bound_names(fn):
    """Names a body may legally LOAD: the args plus every assignment target."""
    bound = set(FACTORY_ARGS)
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
    return bound


def _allowed_string_constant_ids(fn, nodes):
    """``id()``s of the str-Constant nodes that may legally appear: dict keys,
    ``feat(...)`` arguments, subscript-store keys, and the function docstring.
    Every other string literal is rejected (kills `"x" * k` replication and any
    stray string the firewall hasn't reasoned about)."""
    allowed = set()
    if (fn.body and isinstance(fn.body[0], ast.Expr)
            and _is_str_constant(fn.body[0].value)):
        allowed.add(id(fn.body[0].value))
    for node in nodes:
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if _is_str_constant(key):
                    allowed.add(id(key))
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
            s = node.slice
            if getattr(ast, "Index", None) is not None and isinstance(s, ast.Index):
                s = s.value  # pragma: no cover - 3.8 only
            if _is_str_constant(s):
                allowed.add(id(s))
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "feat"):
            for arg in node.args:
                if _is_str_constant(arg):
                    allowed.add(id(arg))
    return allowed


def validate_source(src):
    """Parse and statically prove a generated factory is faithful + safe.

    Returns the parsed :class:`ast.Module` on success; raises
    :class:`FaithfulnessError` (with a human-readable reason) on any violation.
    Pure and side-effect-free — it never executes the code. The checks, in
    order: size caps → parse → exactly-one ``build_schedule`` def with the fixed
    signature → node-type whitelist → no dunder names → loadable-name whitelist
    → call-target whitelist (+ ``feat`` literal-in-registry) → emitted-key
    allow-list (dict literals AND ``params[...]=`` subscripts).
    """
    if not isinstance(src, str):
        raise FaithfulnessError(f"source must be str, got {type(src).__name__}")
    if len(src) > _MAX_SOURCE_CHARS:
        raise FaithfulnessError(
            f"source too long ({len(src)} > {_MAX_SOURCE_CHARS} chars)")
    try:
        tree = ast.parse(src, mode="exec")
    except SyntaxError as exc:
        raise FaithfulnessError(f"generated source does not parse: {exc}")

    fn = _function_def(tree)

    nodes = list(ast.walk(tree))
    if len(nodes) > _MAX_AST_NODES:
        raise FaithfulnessError(
            f"program too large ({len(nodes)} > {_MAX_AST_NODES} AST nodes)")

    allowed_str_ids = _allowed_string_constant_ids(fn, nodes)
    bound = _bound_names(fn)
    for node in nodes:
        if type(node) not in _ALLOWED_NODES:
            raise FaithfulnessError(
                f"disallowed syntax: {type(node).__name__} — the DSL forbids "
                "imports, loops/comprehensions, attribute access, lambdas, "
                "try/with, and augmented assignment (this is the structural "
                "defense against spectral/iterative §1.4-banned features)")

        if isinstance(node, ast.FunctionDef) and node is not fn:
            raise FaithfulnessError(
                "nested function definitions are not allowed — the program is "
                f"exactly one `def {FACTORY_NAME}(...)`")

        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float, str, bool, type(None))):
                raise FaithfulnessError(
                    f"disallowed constant type {type(node.value).__name__}")
            if isinstance(node.value, str) and id(node) not in allowed_str_ids:
                raise FaithfulnessError(
                    "string literals are allowed only as schedule keys, feat() "
                    "feature names, or a docstring (a string in arithmetic could "
                    "replicate into a memory blow-up, e.g. \"x\" * k)")

        elif isinstance(node, ast.Name):
            if node.id.startswith("__"):
                raise FaithfulnessError(
                    f"dunder name {node.id!r} is forbidden (sandbox-escape "
                    "surface)")
            if isinstance(node.ctx, ast.Load) and node.id not in bound \
                    and node.id not in _WHITELIST_GLOBALS:
                raise FaithfulnessError(
                    f"unknown name {node.id!r}: a body may use only its args "
                    f"{FACTORY_ARGS}, local variables, and the helpers "
                    f"{sorted(_WHITELIST_GLOBALS)} — no module/global access")

        elif isinstance(node, ast.arg):
            if node.arg.startswith("__"):
                raise FaithfulnessError(f"dunder arg {node.arg!r} is forbidden")

        elif isinstance(node, ast.Call):
            _check_call(node)

        elif isinstance(node, ast.Dict):
            for key in node.keys:
                _check_emitted_key(key)

        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
            key = _subscript_key(node)
            if key is None:
                raise FaithfulnessError(
                    "a subscript assignment target must use a string-literal "
                    "key (e.g. params[\"opt_branching_radius\"] = ...)")
            _check_emitted_key(ast.Constant(value=key))

    return tree


def _check_call(node):
    """A call must target a whitelisted bare name; ``feat`` takes a registry
    literal; no keyword/`*`/`**` args anywhere."""
    if node.keywords:
        raise FaithfulnessError("keyword arguments are not allowed in the DSL")
    if not isinstance(node.func, ast.Name):
        raise FaithfulnessError(
            "only direct calls to the whitelisted helpers are allowed "
            "(no attribute or computed calls)")
    name = node.func.id
    if name not in _ALLOWED_CALLS:
        raise FaithfulnessError(
            f"call to {name!r} is not allowed — callable surface is "
            f"{sorted(_ALLOWED_CALLS)}")
    for a in node.args:
        if isinstance(a, ast.Starred):
            raise FaithfulnessError("starred call arguments are not allowed")
    if name == "feat":
        if len(node.args) != 1 or not _is_str_constant(node.args[0]):
            raise FaithfulnessError(
                "feat(...) takes exactly one string LITERAL feature name "
                "(provenance check — a computed name could smuggle a banned "
                "feature past the allow-list)")
        fname = node.args[0].value
        if fname not in FEATURE_NAMES:
            raise FaithfulnessError(
                f"feat({fname!r}): not an allow-listed §1.4 feature. Allowed: "
                f"{sorted(FEATURE_NAMES)} (no spectral/LP/iterative features)")


def _check_emitted_key(key_node):
    if not _is_str_constant(key_node):
        raise FaithfulnessError(
            "an emitted schedule key must be a string literal (a computed key "
            "could set a faithfulness-breach param past the static check)")
    key = key_node.value
    if key not in candidate_gate.LEGAL_LEVER_PARAMS:
        raise FaithfulnessError(
            f"{key!r} is not a legal runtime lever (NORTHSTAR §1.6/§5). "
            "A factory may set only the phase-aware levers or "
            "'opt_switch_oracles' — never a budget/cost/termination override")


# --------------------------------------------------------------------------- #
# Restricted execution
# --------------------------------------------------------------------------- #

def _clip(value, lo, hi):
    """The sandbox bounded-θ helper (numpy-clip over scalars and vectors)."""
    return np.clip(value, lo, hi)


def compile_factory(src):
    """Validate (:func:`validate_source`) then compile a generated program into
    its ``build_schedule(n, feat, oracle_budget)`` callable.

    Executes in a sandbox with an EMPTY ``__builtins__`` (so ``__import__`` /
    ``open`` / ``eval`` are unreachable even if a name slipped the static pass)
    and only the whitelisted helpers in globals. Raises
    :class:`FaithfulnessError` on a firewall violation or any exec-time error.
    """
    tree = validate_source(src)
    try:
        # RecursionError: a deeply-nested expression (under the node cap) blows
        # the C stack in compile(); MemoryError: a pathological tree. Both must
        # be a FaithfulnessError, not a raw exception that crashes the loop.
        code = compile(tree, "<m3_llm_factory>", "exec")
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        raise FaithfulnessError(f"generated source did not compile: {exc}")
    sandbox_globals = {
        "__builtins__": {},
        "clip": _clip, "int": int, "round": round, "float": float,
        "min": min, "max": max, "abs": abs, "len": len,
    }
    namespace = {}
    try:
        exec(code, sandbox_globals, namespace)
    except Exception as exc:  # pragma: no cover - defensive
        raise FaithfulnessError(f"generated program failed to define a "
                                f"function: {exc}")
    fn = namespace.get(FACTORY_NAME)
    if not callable(fn):
        raise FaithfulnessError(f"{FACTORY_NAME} was not defined")
    return fn


def _make_feature_accessor(n, c1, c2, c3):
    """The ``feat(name)`` the sandbox sees: the ONLY door to per-variable
    structure, routing every request through the TRUSTED closed §1.4 registry
    (computed in :mod:`benchmarks.m3_proposer`, never in generated code)."""
    registry = {name: fn for name, fn in m3_proposer.FEATURES if name != "none"}

    def feat(name):
        fn = registry.get(name)
        if fn is None:
            raise FaithfulnessError(
                f"feat({name!r}) is not an allow-listed §1.4 feature "
                f"(allowed: {sorted(registry)})")
        vec = fn(n, c1, c2, c3)
        if vec is None:  # pragma: no cover - 'none' excluded above
            raise FaithfulnessError(f"feature {name!r} produced no vector")
        return np.asarray(vec, dtype=float)

    return feat


#: Per-variable array levers (the rest are scalars). These must realize as a
#: finite length-n vector — anything else is a malformed lever (§1.7 bounded θ).
_VECTOR_LEVER_SUFFIXES = ("branching_weights", "variable_priorities")


def make_candidate_factory(build_schedule):
    """Wrap a sandbox ``build_schedule(n, feat, oracle_budget)`` into the
    ``factory(n, c1, c2, c3)`` the harness expects — FAIL-LOUD at every ``n``.

    The wrapper is the per-call faithfulness/fail-loud boundary (§2.1): a
    ``build_schedule`` that crashes (an ``OverflowError`` on a giant int, a
    ``TypeError``, …), returns a non-dict, emits an illegal key, or yields a
    non-numeric / non-finite / wrong-shape value at ANY ``n`` is converted to a
    :class:`FaithfulnessError`. So even when the §10 gate or the solver resolves
    the factory in-process at a stratum the smoke test didn't cover, a bad
    realization surfaces as a recorded rejection, never a raw crash of the loop.
    """
    def factory(n, c1, c2, c3):
        feat = _make_feature_accessor(n, c1, c2, c3)
        try:
            params = build_schedule(n, feat, metric.oracle_budget)
        except FaithfulnessError:
            raise
        except Exception as exc:
            raise FaithfulnessError(f"{FACTORY_NAME} crashed at n={n}: {exc!r}")
        if not isinstance(params, dict):
            raise FaithfulnessError(
                f"{FACTORY_NAME} must return a dict, got {type(params).__name__}")
        for key, value in params.items():
            if key not in candidate_gate.LEGAL_LEVER_PARAMS:
                raise FaithfulnessError(
                    f"runtime-emitted key {key!r} is not a legal lever")
            try:
                arr = np.asarray(value, dtype=float)
            except (TypeError, ValueError) as exc:
                raise FaithfulnessError(
                    f"emitted {key!r} is not numeric at n={n}: {exc!r}")
            if not np.all(np.isfinite(arr)):
                raise FaithfulnessError(
                    f"emitted {key!r} has non-finite values at n={n}")
            if key.endswith(_VECTOR_LEVER_SUFFIXES) and arr.shape != (n,):
                raise FaithfulnessError(
                    f"{key!r} must be a length-n vector at n={n}, got shape "
                    f"{arr.shape}")
        return params

    return factory


def _smoke_child(src, strata, mem_bytes, cpu_s, out_q):
    """Run inside the forked smoke subprocess: best-effort cap memory + CPU,
    rebuild the factory from ``src``, and resolve it at every stratum (the
    fail-loud wrapper validates each). Reports ``("ok"|"fail", message)``; a
    runtime/memory blow-up never returns (the parent kills it on timeout)."""
    if _resource is not None:  # pragma: no branch - POSIX
        for lim_name, cap in (("RLIMIT_AS", mem_bytes), ("RLIMIT_DATA", mem_bytes),
                              ("RLIMIT_CPU", cpu_s)):
            lim = getattr(_resource, lim_name, None)
            if lim is None:
                continue
            try:
                _soft, hard = _resource.getrlimit(lim)
                new = cap if (hard == _resource.RLIM_INFINITY or cap < hard) else hard
                _resource.setrlimit(lim, (new, hard))
            except (ValueError, OSError):  # pragma: no cover - platform dependent
                pass  # best-effort; the wall-clock kill is the hard guarantee
    try:
        from benchmarks.synthetic_eq29 import make_matrices
    except ImportError:  # pragma: no cover - flat layout fallback
        from synthetic_eq29 import make_matrices  # type: ignore
    try:
        factory = make_candidate_factory(compile_factory(src))
        for n in strata:
            c1, c2, c3 = make_matrices(n, index=0)
            factory(n, c1, c2, c3)  # the wrapper validates shape/finiteness
        out_q.put(("ok", ""))
    except FaithfulnessError as exc:
        out_q.put(("fail", str(exc)))
    except Exception as exc:  # pragma: no cover - defensive
        out_q.put(("fail", f"{type(exc).__name__}: {exc}"))


def _bounded_smoke(src, *, strata, timeout, mem_mb, cpu_s):
    """Resolve the factory at ``strata`` inside a killable, resource-bounded
    subprocess. Raises :class:`FaithfulnessError` on a validation failure OR a
    budget overrun (the only reliable defense against a loop-free bignum CPU /
    memory blow-up the static pass cannot see). Falls back to an in-process run
    on a platform without ``fork`` — there the static guards + fail-loud wrapper
    carry safety, minus the hard CPU/mem bound."""
    try:
        ctx = multiprocessing.get_context("fork")
    except (ValueError, AttributeError):  # pragma: no cover - non-fork platform
        factory = make_candidate_factory(compile_factory(src))
        try:
            from benchmarks.synthetic_eq29 import make_matrices
        except ImportError:  # pragma: no cover
            from synthetic_eq29 import make_matrices  # type: ignore
        for n in strata:
            factory(n, *make_matrices(n, index=0))
        return
    out_q = ctx.Queue()
    proc = ctx.Process(target=_smoke_child,
                       args=(src, tuple(strata), mem_mb * 1024 * 1024, cpu_s, out_q))
    proc.start()
    try:
        status, message = out_q.get(timeout=timeout)
    except _queue.Empty:
        status, message = None, None
    finally:
        if proc.is_alive():
            proc.terminate()
            proc.join(1.0)
            if proc.is_alive():  # pragma: no cover - stubborn child
                proc.kill()
                proc.join(1.0)
        else:
            proc.join(1.0)
    if status is None:
        raise FaithfulnessError(
            f"factory exceeded the smoke budget (>{timeout}s wall / {mem_mb}MB "
            f"/ {cpu_s}s CPU) across strata {tuple(strata)} — a runtime/memory "
            "blow-up, rejected before the solve")
    if status != "ok":
        raise FaithfulnessError(f"factory failed smoke validation: {message}")


def compile_candidate_factory(src, *, strata=SMOKE_STRATA, timeout=SMOKE_TIMEOUT_S,
                              mem_mb=SMOKE_MEM_MB, cpu_s=SMOKE_CPU_S):
    """Validate, compile, wrap, and resource-bounded-smoke a generated program
    into a ``factory(n, c1, c2, c3)`` ready for :class:`benchmarks.m3.Candidate`.

    The single entry point a proposer calls; raises :class:`FaithfulnessError`
    on any firewall violation, a factory that crashes / emits garbage at a smoke
    stratum, or a runtime/memory blow-up that overruns the subprocess budget.
    ``strata`` covers the small-n compression regime plus the sizes the §10 gate
    re-resolves at (``candidate_gate.admit`` ``scale_ns``), so an ``if n > k``
    payload detonates during validation, not during the solve.
    """
    factory = make_candidate_factory(compile_factory(src))
    _bounded_smoke(src, strata=strata, timeout=timeout, mem_mb=mem_mb, cpu_s=cpu_s)
    return factory


# --------------------------------------------------------------------------- #
# Genome bridge — render a parametric genome as DSL source (exemplar seeding)
# --------------------------------------------------------------------------- #

#: A canonical default-equivalent program (emits ``{}`` == the CBQS default
#: path). The neutral exemplar shown when no scored candidate has source yet,
#: and a firewall-valid template the LLM can mutate.
BASELINE_SOURCE = (
    "def build_schedule(n, feat, oracle_budget):\n"
    "    # CBQS default: no lever overrides.\n"
    "    return {}\n"
)


def genome_to_source(genome):
    """Render an :mod:`benchmarks.m3_proposer` genome as firewall-valid DSL
    source — the bridge that lets the LLM proposer bootstrap exemplars from the
    parametric population (and round-trip equivalently; see the tests).

    Decodes the same 5-gene layout as
    :func:`benchmarks.m3_proposer.genome_to_factory` (r_opt_sat, r_opt,
    alpha_switch, theta_amp, theta_feature) and emits the matching
    ``build_schedule`` body.
    """
    g = m3_proposer.clamp_genome(genome)
    r_opt_sat, r_opt, alpha, theta_amp, theta_feat = (float(x) for x in g)
    feat_name = m3_proposer.FEATURES[int(np.floor(theta_feat))][0]
    lines = [
        f"def {FACTORY_NAME}(n, feat, oracle_budget):",
        "    params = {",
        f"        \"opt_sat_branching_radius\": {r_opt_sat!r},",
        f"        \"opt_branching_radius\": {r_opt!r},",
        f"        \"opt_switch_oracles\": int(round({alpha!r} * oracle_budget(n))),",
        "    }",
    ]
    if theta_amp > 0.0 and feat_name != "none":
        lines.append(
            f"    params[\"opt_branching_weights\"] = "
            f"clip({theta_amp!r} * feat({feat_name!r}), -0.5, 0.5)")
    lines.append("    return params")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Prompt assembly (FunSearch)
# --------------------------------------------------------------------------- #

def _system_prompt():
    """The frozen DSL contract the LLM writes against (kept cache-stable: no
    per-request data — features/levers/bounds are derived from the registries
    so the contract can never drift from the firewall)."""
    feats = ", ".join(f'"{n}"' for n in sorted(FEATURE_NAMES))
    return (
        "You are evolving a bias schedule for a quantum-faithful constrained "
        "search solver (CBQS). You write ONE Python function and nothing else:\n\n"
        f"    def {FACTORY_NAME}(n, feat, oracle_budget):\n"
        "        ...\n"
        f"        return {{...}}   # dict of lever -> value\n\n"
        "STRICT DSL — violating any rule means your program is rejected unrun:\n"
        "  * Define exactly one function with that exact signature. No imports, "
        "no other top-level statements.\n"
        "  * No loops, comprehensions, attribute access (no `.foo`), lambdas, "
        "try/with, or `__`-names. Only `if/else`, arithmetic, and calls to the "
        "helpers below.\n"
        "  * Helpers available (and nothing else): clip(x, lo, hi), int, round, "
        "float, min, max, abs, len.\n"
        "  * `n` is the number of variables. `oracle_budget(n)` returns the "
        "per-worker oracle budget T(n).\n"
        f"  * `feat(name)` returns a bounded length-n vector in [-1, 1] for an "
        f"allow-listed feature. Allowed names ONLY: {feats}. "
        "These are the only per-variable signals you may use — there is no way "
        "to compute your own from the problem matrices (spectral, LP, and "
        "iterative graph statistics are forbidden).\n\n"
        "Levers you may set (any subset; omit to keep the default):\n"
        "  * \"opt_sat_branching_radius\", \"opt_branching_radius\": target "
        "neighborhood radius r in [1.5, 8] for the tighten / explore phases "
        "(the C core sets bias = n/r - 2). Smaller r = a tighter local search.\n"
        "  * \"opt_switch_oracles\": when to switch exploit->explore, as an "
        "oracle count. Use int(round(alpha * oracle_budget(n))) with alpha in "
        "[0, 0.25].\n"
        "  * \"opt_branching_weights\": a per-variable logit offset theta "
        "(opt phase). Use clip(amp * feat(name), -0.5, 0.5) with |amp| <= 0.5.\n\n"
        "Goal: LOWER primal-integral PI (faster, deeper objective) while staying "
        "feasible and scale-invariant across n. Propose ONE new program that "
        "improves on the exemplars. Return ONLY a ```python code block with the "
        "function — no prose."
    )


def _describe_individual(ind, rank):
    """One exemplar block: its source + a compact 'observed anytime curve'
    (per-size W and median PI from the verdict, else the fitness summary)."""
    src = exemplar_source(ind)
    fit = getattr(ind, "fitness", None)
    lines = [f"### Exemplar {rank} (fitness: {fit!r})"]
    verdict = getattr(ind, "verdict", None)
    if verdict:
        per_size = verdict.get("aggregation", {}).get("per_size", {})
        curve = ", ".join(
            f"n={n}: W={rec.get('W')}, medPI={rec.get('median_PI')}"
            for n, rec in sorted(per_size.items()))
        if curve:
            lines.append(f"observed: {curve}")
    lines.append("```python")
    lines.append(src.rstrip("\n"))
    lines.append("```")
    return "\n".join(lines)


def exemplar_source(ind):
    """Source code for an exemplar: its own generated source if it has one
    (LLM candidate), else rendered from its parametric genome, else the
    neutral baseline. Always returns firewall-valid source."""
    cand = getattr(ind, "candidate", ind)
    meta = getattr(cand, "meta", None) or {}
    if meta.get("source"):
        return meta["source"]
    genome = getattr(cand, "genome", None)
    if genome is not None:
        try:
            if len(tuple(genome)) == len(m3_proposer.GENES):
                return genome_to_source(genome)
        except (TypeError, ValueError):
            pass
    return BASELINE_SOURCE


def build_prompt(exemplars, *, nonce=0):
    """Assemble the (system, user) FunSearch prompt from high-scoring exemplars.

    ``exemplars`` is an iterable of :class:`benchmarks.m3.Individual` (already
    ranked best-first). ``nonce`` varies the user turn across the offspring of
    one generation so identical exemplars don't yield identical requests (mild
    diversity pressure without touching the cache-stable system prompt).
    """
    exemplars = list(exemplars)
    if not exemplars:
        blocks = ["### Exemplar 1 (the CBQS default)", "```python",
                  BASELINE_SOURCE.rstrip("\n"), "```"]
    else:
        blocks = [_describe_individual(ind, i + 1)
                  for i, ind in enumerate(exemplars)]
    user = (
        "Here are the current best schedules and how they scored:\n\n"
        + "\n\n".join(blocks)
        + f"\n\nPropose improved schedule #{nonce + 1}. Return ONLY the "
        "```python function."
    )
    return _system_prompt(), user


_CODE_FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)


def extract_code(text):
    """Pull the (first) fenced ```python block from an LLM response, or treat
    the whole text as code if unfenced. Raises :class:`FaithfulnessError` on
    empty input (a non-response is not a candidate)."""
    if not isinstance(text, str) or not text.strip():
        raise FaithfulnessError("empty LLM response — no program to compile")
    match = _CODE_FENCE.search(text)
    code = match.group(1) if match else text
    if not code.strip():
        raise FaithfulnessError("LLM response has an empty code block")
    return code


def _source_fingerprint(src):
    """A stable 1-tuple genome for an LLM candidate (NORTHSTAR §10 'a code
    hash'): identical source dedups (distance 0), any difference stays distinct
    (the parametric genome's Euclidean diversity does not apply to code)."""
    digest = hashlib.blake2b(src.encode("utf-8"), digest_size=8).digest()
    return (float(int.from_bytes(digest, "big")),)


# --------------------------------------------------------------------------- #
# The proposer
# --------------------------------------------------------------------------- #

class LLMProposer:
    """LLM-FunSearch ``proposer(population, rng) -> list[Candidate]`` (§10).

    Each call: take the fittest ``n_exemplars`` parents, build a FunSearch
    prompt (their source + observed curves), ask the ``llm_client`` for
    ``n_offspring`` new programs, run each through the firewall
    (:func:`compile_candidate_factory`), and wrap the survivors as
    :class:`benchmarks.m3.Candidate` carrying the source + provenance. A program
    that fails the firewall is DROPPED (recorded in :attr:`rejections`), never
    crashed — so one bad generation can't sink a long ``evolve`` run; if every
    program fails, an empty list is returned (``evolve`` handles it).

    ``llm_client`` is ``callable(system: str, user: str) -> str`` — pluggable so
    the loop is testable with :class:`FakeLLMClient` (no network).
    """

    def __init__(self, llm_client, *, n_offspring=4, n_exemplars=3,
                 id_prefix="llm", smoke_strata=SMOKE_STRATA):
        if not callable(llm_client):
            raise ValueError("llm_client must be callable(system, user) -> str")
        if n_offspring < 1:
            raise ValueError(f"n_offspring must be >= 1, got {n_offspring}")
        if n_exemplars < 1:
            raise ValueError(f"n_exemplars must be >= 1, got {n_exemplars}")
        self.llm_client = llm_client
        self.n_offspring = int(n_offspring)
        self.n_exemplars = int(n_exemplars)
        self.id_prefix = str(id_prefix)
        self.smoke_strata = tuple(smoke_strata)
        self._next_id = 0
        #: (source, reason) for every firewall-rejected generation — the §13
        #: audit trail (and a no-silent-cap signal: the caller can see how many
        #: ideas were discarded vs accepted).
        self.rejections = []

    def _make_id(self):
        cid = f"{self.id_prefix}_{self._next_id}"
        self._next_id += 1
        return cid

    def __call__(self, population, rng):
        exemplars = sorted(
            population, key=lambda ind: ind.fitness, reverse=True
        )[:self.n_exemplars]
        out = []
        for i in range(self.n_offspring):
            system, user = build_prompt(exemplars, nonce=i)
            src = None
            try:
                text = self.llm_client(system, user)
                src = extract_code(text)
                factory = compile_candidate_factory(src, strata=self.smoke_strata)
            except FaithfulnessError as exc:
                self.rejections.append((src, str(exc)))
                continue
            out.append(Candidate(
                factory=factory,
                genome=_source_fingerprint(src),
                meta={"id": self._make_id(), "op": "llm", "source": src}))
        return out


# --------------------------------------------------------------------------- #
# LLM clients
# --------------------------------------------------------------------------- #

class FakeLLMClient:
    """A deterministic offline ``llm_client`` for tests and the negative control.

    Returns the configured ``responses`` in order (cycling), ignoring the
    prompt, so the firewall + loop are exercised with no network. Each response
    is the raw model TEXT (typically a ```python block)."""

    def __init__(self, responses):
        self.responses = list(responses)
        if not self.responses:
            raise ValueError("FakeLLMClient needs at least one response")
        self.calls = []
        self._i = 0

    def __call__(self, system, user):
        self.calls.append((system, user))
        resp = self.responses[self._i % len(self.responses)]
        self._i += 1
        return resp


class AnthropicLLMClient:
    """Optional real ``llm_client`` backed by the Anthropic SDK (Claude).

    ``anthropic`` is imported LAZILY in ``__init__`` so it is NOT a hard
    dependency of this benchmark package — tests and the parametric path never
    import it, and a machine without the SDK can still ``import
    benchmarks.m3_codegen``. Constructing this client without the SDK installed
    raises a clear error; calling it spends API tokens, so it is opt-in only.
    """

    def __init__(self, *, model="claude-opus-4-8", max_tokens=4096,
                 effort="high", client=None):
        if client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - env dependent
                raise ImportError(
                    "AnthropicLLMClient needs the 'anthropic' package "
                    "(pip install anthropic); it is an optional dependency"
                ) from exc
            client = anthropic.Anthropic()
        self._client = client
        self.model = model
        self.max_tokens = int(max_tokens)
        self.effort = effort

    def __call__(self, system, user):
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in resp.content
            if getattr(block, "type", None) == "text")
