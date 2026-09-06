"""Shared AST proof utilities for the Task #90 global acceptance proof.

Non-collected (underscore prefix) support for
``test_phase15_e2a_task90_global_acceptance_proof``: pure ``ast`` shape
verifiers and parsed-only fixture builders for the selected live
acceptance test, the sanitized-env builder, the live cells helper source,
and the binding/serializer support module source.

This helper NEVER creates a session, NEVER accesses environment
variables, NEVER accesses a database or Docker, and NEVER alters default
pytest collection behavior (the ``_`` prefix keeps it out of default
collection). It only parses source text and inspects ASTs; fixtures built
here are parsed only, never executed.
"""

from __future__ import annotations

import ast

from ._phase15_e2a_task90_types import (
    REQUIRED_OBSERVATION_FIELDS,
    SANITIZED_ALLOWLIST as _SANITIZED_ALLOWLIST,
    SENSITIVE_ENV_VARS as _SENSITIVE_ENV_VARS,
)

LIVE_TEST_NAME = "test_task90_authorized_live_acceptance"
METADATA_TEST_NAME = "test_task90_live_acceptance_metadata"
HELPER_IMPL_FUNCTION = "_run_task90_live_proof"
LIVE_SELECTOR_FILENAME = "phase15_e2a_task90_live_acceptance.py"
LIVE_CELLS_FILENAME = "_phase15_e2a_task90_live_cells.py"
SUPPORT_FILENAME = "_phase15_e2a_task90_support.py"
TYPES_FILENAME = "_phase15_e2a_task90_types.py"

# Real production boundaries the Task #90 live cells module MUST reference:
# the default E2aReconciler construction (with no injected repository or
# builder), the real strict corpus admission surface, the full-collection
# scope snapshot builder, the single-use producer build token, and the
# binding construction + verification.
_REQUIRED_LIVE_CELLS_SOURCE_FRAGMENTS = (
    "E2aReconciler()",
    "admit_e2a_corpus",
    "BundleAuthority",
    "make_task90_scope_snapshot",
    "Task90ScopeSnapshot",
    "acquire_build_token",
    "build_evidence_binding",
    ".verify()",
    "artifact_dict",
)

# Fake/replacement machinery, environment/secret access, session/DB
# construction at module level, test-framework machinery, and the protected
# historical runner that must NEVER appear in the Task #90 live cells module.
_FORBIDDEN_LIVE_CELLS_FRAGMENTS = (
    "unittest.mock",
    "MagicMock",
    "monkeypatch",
    "create_autospec",
    "patch(",
    "NotImplementedError",
    "import pytest",
    "pytest.",
    "skip(",
    "xfail(",
    "os.environ",
    "getenv",
    "DATABASE_URL",
    "PGHOST",
    "PGUSER",
    "PGPASSWORD",
    "OPENAI_API_KEY",
    "run_e2a_verification",
    "spec_from_file_location",
    "DisposableE2aSession(",
)

# The default-reconciler guard is AST-based (see ``_verify_live_cells_source``):
# every ``E2aReconciler(...)`` call must be the zero-argument form with NO
# injected repository or builder.

# Fragments the binding/serializer support module MUST reference: the
# runtime ``dataclasses.fields`` digest derivation, the exact production
# result type, the single-use build token, the redacted artifact dict, and
# the canonical digest surface.
_REQUIRED_SUPPORT_SOURCE_FRAGMENTS = (
    "dataclasses.fields",
    "E2aReconciliationResult",
    "acquire_build_token",
    "build_evidence_binding",
    "artifact_dict",
    "canonical_json_sha256",
    "TASK90_CANONICAL_ROUTE",
    "Task90ScopeSnapshot",
)

# Environment/secret access, database/Docker imports, session construction,
# mock/fake machinery, unsafe dynamic imports, exec/eval, subprocess, and
# the protected historical runner that must NEVER appear in the support
# (binding/serializer) module.
_FORBIDDEN_SUPPORT_FRAGMENTS = (
    "os.environ",
    "getenv",
    "DATABASE_URL",
    "PGHOST",
    "PGUSER",
    "PGPASSWORD",
    "OPENAI_API_KEY",
    "import psycopg",
    "psycopg",
    "import pytest",
    "pytest.",
    "skip(",
    "xfail(",
    "unittest.mock",
    "MagicMock",
    "monkeypatch",
    "create_autospec",
    "patch(",
    "DisposableE2aSession(",
    "open_fresh_attested_connection",
    "run_e2a_verification",
    "__import__",
    "importlib.import_module",
    "exec(",
    "eval(",
    "compile(",
    "subprocess",
)


def _single_function_by_name(tree: ast.Module, function_name: str) -> ast.FunctionDef:
    """Return the single top-level function with the given name.

    The named function must exist exactly once at module top level; any
    other shape (missing or duplicated) fails the guard.
    """
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    ]
    assert (
        len(functions) == 1
    ), f"the {function_name!r} function must exist exactly once"
    return functions[0]


def _is_direct_getenv_call(call: ast.Call) -> bool:
    """True only for the direct zero-keyword ``os.getenv(<one arg>)`` form."""
    if call.keywords:
        return False
    if not isinstance(call.func, ast.Attribute):
        return False
    if call.func.attr != "getenv":
        return False
    if not (isinstance(call.func.value, ast.Name) and call.func.value.id == "os"):
        return False
    return len(call.args) == 1


def _verify_sanitized_env_structure(function: ast.FunctionDef) -> None:
    """Structural proof for the allowlist builder's environment reads.

    Accepts ONLY direct zero-keyword ``os.getenv("<literal key>")`` calls;
    every attribute access anywhere in the builder must be exactly the
    direct ``os.getenv`` form. The collected literal keys must equal the
    allowlist exactly and stay disjoint from the sensitive variable names.
    """
    getenv_keys: list[str] = []
    for node in ast.walk(function):
        if isinstance(node, ast.Attribute):
            assert (
                isinstance(node.value, ast.Name)
                and node.value.id == "os"
                and node.attr == "getenv"
            ), (
                "every attribute access in the allowlist builder must be "
                "exactly the direct os.getenv form"
            )
        if not isinstance(node, ast.Call):
            continue
        assert _is_direct_getenv_call(node), (
            "every call in the allowlist builder must be the direct "
            "zero-keyword os.getenv(<literal key>) form"
        )
        argument = node.args[0]
        assert isinstance(argument, ast.Constant) and isinstance(
            argument.value, str
        ), "os.getenv key must be a string literal"
        getenv_keys.append(argument.value)
    assert getenv_keys, "_sanitized_env must read allowlisted keys via os.getenv"
    assert set(getenv_keys) == set(
        _SANITIZED_ALLOWLIST
    ), "os.getenv keys must match the explicit allowlist exactly"
    assert not (
        set(_SANITIZED_ALLOWLIST) & _SENSITIVE_ENV_VARS
    ), "the allowlist must never contain sensitive variable names"
    assert not any(
        key in _SENSITIVE_ENV_VARS for key in getenv_keys
    ), "no sensitive variable may be read individually"


def _verify_session_keyword_value(keyword: ast.keyword) -> None:
    """Structural proof of one session keyword's value expression.

    Each keyword must bind EXACTLY the approved safe expression:

    - ``container_name=_validate_container_name(_generate_safe_container_name())``
    - ``port=_select_ephemeral_port()``
    - ``password=_generate_test_password()``
    """
    assert keyword.arg is not None, "session keyword must be named"
    value = keyword.value
    if keyword.arg == "container_name":
        assert isinstance(value, ast.Call) and isinstance(
            value.func, ast.Name
        ), "container_name must be _validate_container_name(_generate_safe_container_name())"
        assert (
            value.func.id == "_validate_container_name"
        ), "container_name must pass through _validate_container_name(...)"
        assert not value.keywords, "container_name must receive no keyword arguments"
        assert len(value.args) == 1, "container_name must receive exactly one argument"
        inner = value.args[0]
        assert isinstance(inner, ast.Call) and isinstance(
            inner.func, ast.Name
        ), "the container_name argument must be _generate_safe_container_name()"
        assert (
            inner.func.id == "_generate_safe_container_name"
        ), "the container_name argument must be _generate_safe_container_name()"
        assert (
            not inner.args and not inner.keywords
        ), "_generate_safe_container_name() must be a zero-argument call"
    elif keyword.arg == "port":
        assert isinstance(value, ast.Call) and isinstance(
            value.func, ast.Name
        ), "port must be _select_ephemeral_port()"
        assert (
            value.func.id == "_select_ephemeral_port"
        ), "port must be _select_ephemeral_port()"
        assert (
            not value.args and not value.keywords
        ), "_select_ephemeral_port() must be a zero-argument call"
    elif keyword.arg == "password":
        assert isinstance(value, ast.Call) and isinstance(
            value.func, ast.Name
        ), "password must be _generate_test_password()"
        assert (
            value.func.id == "_generate_test_password"
        ), "password must be _generate_test_password()"
        assert (
            not value.args and not value.keywords
        ), "_generate_test_password() must be a zero-argument call"
    else:
        raise AssertionError(f"unexpected session keyword: {keyword.arg}")


def _verify_live_acceptance_body(function: ast.FunctionDef) -> None:
    """Structural proof of the selected live test's exact body.

    The function must be undecorated, and its ENTIRE body (after at most
    one optional leading docstring) must be exactly:

    - the bare no-argument, no-keyword ``_require_authorization()`` call
      as the FIRST statement (auth first; never skipped),
    - exactly one ``with contextlib.ExitStack() as stack:`` block that
      constructs exactly one ``DisposableE2aSession(...)`` reusing the
      safe generated container name / ephemeral port / generated password
      (keyword-only, no positional arguments), enters it exactly once via
      ``stack.enter_context(session)``, and invokes
      ``_run_task90_live_proof(session)`` exactly once as a direct
      positional call with only the session argument,
    - exactly one ``if not observations.success:`` failure raise:
      ``RuntimeError`` whose message interpolates ONLY
      ``observations.error_reason`` after a fixed prefix,
    - exactly ``len(REQUIRED_OBSERVATION_FIELDS)`` success assertions, each
      of the form ``assert observations.<field>``, covering every required
      observation field exactly once.

    The live test must never call ``session.open_fresh_attested_connection``
    itself.
    """
    assert not function.decorator_list, "the selected live test must not be decorated"
    statements = list(function.body)
    if (
        statements
        and isinstance(statements[0], ast.Expr)
        and isinstance(statements[0].value, ast.Constant)
        and isinstance(statements[0].value.value, str)
    ):
        statements = statements[1:]
    assert statements, "the selected live test body must not be empty"

    first_statement = statements[0]
    assert isinstance(first_statement, ast.Expr) and isinstance(
        first_statement.value, ast.Call
    ), "the first live-test body statement must be the bare _require_authorization() call"
    auth_call = first_statement.value
    assert isinstance(
        auth_call.func, ast.Name
    ), "the first live-test call must be the direct _require_authorization()"
    assert (
        auth_call.func.id == "_require_authorization"
    ), "the first live-test call must be _require_authorization()"
    assert (
        not auth_call.args and not auth_call.keywords
    ), "_require_authorization() must be a no-argument, no-keyword call"

    with_nodes = [node for node in statements if isinstance(node, ast.With)]
    assert (
        len(with_nodes) == 1
    ), "the live test body must use exactly one ExitStack context manager"
    with_node = with_nodes[0]
    context = with_node.items[0].context_expr
    assert isinstance(context, ast.Call), "the ExitStack must be entered by calling it"
    exit_stack_func = context.func
    assert (
        isinstance(exit_stack_func, ast.Name) and exit_stack_func.id == "ExitStack"
    ) or (
        isinstance(exit_stack_func, ast.Attribute)
        and exit_stack_func.attr == "ExitStack"
    ), "the with statement must enter exactly one ExitStack"
    assert not context.args and not context.keywords, "ExitStack() takes no arguments"

    session_calls = [
        node
        for node in ast.walk(with_node)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "DisposableE2aSession"
    ]
    assert (
        len(session_calls) == 1
    ), "the live test must construct exactly one DisposableE2aSession"
    session_call = session_calls[0]
    assert not session_call.args, "the session must be constructed with keywords only"
    assert all(
        keyword.arg is not None for keyword in session_call.keywords
    ), "the session must receive no **kwargs"
    session_keywords = {keyword.arg for keyword in session_call.keywords}
    assert session_keywords == {
        "container_name",
        "port",
        "password",
    }, "the session must reuse exactly the safe container-name/port/password values"
    for keyword in session_call.keywords:
        _verify_session_keyword_value(keyword)

    enter_calls = [
        node
        for node in ast.walk(with_node)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "enter_context"
    ]
    assert len(enter_calls) == 1, "the session must be entered exactly once"
    enter_arguments = enter_calls[0].args
    assert len(enter_arguments) == 1 and isinstance(
        enter_arguments[0], ast.Name
    ), "enter_context must receive exactly the session object"
    assert enter_arguments[0].id == "session", "enter_context must receive the session"

    impl_calls = [
        node
        for node in ast.walk(with_node)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == HELPER_IMPL_FUNCTION
    ]
    assert (
        len(impl_calls) == 1
    ), "the live test must invoke _run_task90_live_proof exactly once"
    assert not impl_calls[0].keywords, "the helper must be invoked positionally"
    assert (
        len(impl_calls[0].args) == 1
    ), "the helper must receive exactly the session as its only argument"
    helper_argument = impl_calls[0].args[0]
    assert (
        isinstance(helper_argument, ast.Name) and helper_argument.id == "session"
    ), "the helper argument must be exactly the session object"

    attribute_names = {
        node.attr for node in ast.walk(function) if isinstance(node, ast.Attribute)
    }
    assert (
        "open_fresh_attested_connection" not in attribute_names
    ), "the live test must not open connections itself"

    failure_guards = [
        statement for statement in statements if isinstance(statement, ast.If)
    ]
    assert (
        len(failure_guards) == 1
    ), "the failure raise must sit in exactly one if guard"
    failure_test = failure_guards[0].test
    assert (
        isinstance(failure_test, ast.UnaryOp)
        and isinstance(failure_test.op, ast.Not)
        and isinstance(failure_test.operand, ast.Attribute)
        and failure_test.operand.attr == "success"
        and isinstance(failure_test.operand.value, ast.Name)
        and failure_test.operand.value.id == "observations"
    ), "the failure raise must be guarded by 'if not observations.success:'"

    raises = [node for node in ast.walk(function) if isinstance(node, ast.Raise)]
    assert len(raises) == 1, "the live test must raise exactly once"
    exc = raises[0].exc
    assert isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name)
    assert exc.func.id == "RuntimeError" and len(exc.args) == 1
    message = exc.args[0]
    assert isinstance(
        message, ast.JoinedStr
    ), "the RuntimeError message must be an f-string"
    parts = message.values
    assert isinstance(parts[0], ast.Constant) and isinstance(
        parts[0].value, str
    ), "the RuntimeError message must carry a fixed text prefix"
    dynamic_parts = [part for part in parts if isinstance(part, ast.FormattedValue)]
    assert (
        len(dynamic_parts) == 1
    ), "only the bounded observations.error_reason may be interpolated"
    reason = dynamic_parts[0].value
    assert isinstance(reason, ast.Attribute) and reason.attr == "error_reason"
    assert isinstance(reason.value, ast.Name) and reason.value.id == "observations"

    assertions = [node for node in ast.walk(function) if isinstance(node, ast.Assert)]
    assert len(assertions) == len(REQUIRED_OBSERVATION_FIELDS), (
        "the live test must make exactly one success assertion per required "
        "observation field"
    )
    asserted_fields: set[str] = set()
    for node in assertions:
        test = node.test
        assert isinstance(test, ast.Attribute) and isinstance(test.value, ast.Name)
        assert (
            test.value.id == "observations"
        ), "every success assertion must be assert observations.<field>"
        asserted_fields.add(test.attr)
    assert asserted_fields == set(
        REQUIRED_OBSERVATION_FIELDS
    ), "every required observation field must be asserted exactly once"


def _verify_live_cells_source(source: str) -> None:
    """Source-level pins for the Task #90 live cells module.

    The module must reference the default reconciler construction, the real
    strict corpus admission, the full-collection scope snapshot, the
    single-use producer token, and the binding build/verify/artifact
    surface; and must never contain environment reads, secret names,
    session construction, test-framework machinery, the protected
    historical runner, or fake/replacement machinery.

    The default-reconciler guard is AST-based: every ``E2aReconciler(...)``
    call in the module must be the zero-argument form (default repository
    and builder only). A plain substring check is unreliable because the
    Task90 observation field ``default_reconciler_default_repository``
    legitimately contains the substring ``repository=``.
    """
    for required in _REQUIRED_LIVE_CELLS_SOURCE_FRAGMENTS:
        assert required in source, f"live cells must reference {required!r}"
    for forbidden in _FORBIDDEN_LIVE_CELLS_FRAGMENTS:
        assert forbidden not in source, f"live cells must not contain {forbidden!r}"
    tree = ast.parse(source)
    reconciler_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "E2aReconciler"
    ]
    assert reconciler_calls, "live cells must construct the default E2aReconciler()"
    for call in reconciler_calls:
        assert (
            not call.args
        ), "E2aReconciler must be constructed with no positional args"
        assert (
            not call.keywords
        ), "E2aReconciler must be constructed with no injected repository/builder keyword"


def _is_session_attested_connection_call(call: ast.Call) -> bool:
    """True only for the direct no-argument ``session.open_fresh_attested_connection()``."""
    if call.args or call.keywords:
        return False
    if not isinstance(call.func, ast.Attribute):
        return False
    if call.func.attr != "open_fresh_attested_connection":
        return False
    return isinstance(call.func.value, ast.Name) and call.func.value.id == "session"


def _verify_task90_parent_registration_pin(function: ast.FunctionDef) -> None:
    """Structural proof of the harness parent-registration precondition.

    Inside ``_run_task90_live_proof`` the admitted parents must be registered
    on a fresh caller-owned connection BEFORE the first real reconcile, and
    that exact connection must be closed in the ``finally`` cleanup block:

    - EXACTLY one ``_register_task90_parents(<named-connection>, desired)``
      call performs the registration, passing that exact named connection and
      the admitted ``desired`` state positionally,
    - the registration connection is assigned EXACTLY once, from the direct
      ``session.open_fresh_attested_connection()`` factory, and that fresh
      assignment MUST precede the registration call (never reused or taken
      from a stale/non-session source, and never assigned fresh only AFTER
      the registration),
    - every real reconcile is EXACTLY ``reconciler.reconcile(...)`` (a
      look-alike receiver that merely exposes ``.reconcile`` is rejected), and
      the registration precedes the first such real reconcile,
    - a ``_close_quietly(<same-connection>)`` call sits in the ``finally``
      body, so the fresh connection cannot leak.
    """
    register_calls: list[ast.Call] = []
    fresh_assignments: list[tuple[int, str]] = []
    reconcile_calls: list[tuple[int, ast.Call]] = []
    for node in ast.walk(function):
        if isinstance(node, ast.Assign):
            if (
                len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Call)
                and _is_session_attested_connection_call(node.value)
            ):
                fresh_assignments.append((node.lineno, node.targets[0].id))
        if not isinstance(node, ast.Call):
            continue
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "_register_task90_parents"
        ):
            register_calls.append(node)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "reconcile":
            reconcile_calls.append((node.lineno, node))

    assert (
        len(register_calls) == 1
    ), "the live proof must call _register_task90_parents exactly once"
    register_call = register_calls[0]
    assert (
        not register_call.keywords
    ), "parent registration must pass the connection and desired positionally"
    assert (
        len(register_call.args) == 2
    ), "parent registration must receive exactly (connection, desired)"
    connection_arg = register_call.args[0]
    assert isinstance(
        connection_arg, ast.Name
    ), "parent registration must use a named fresh connection"
    connection_name = connection_arg.id
    desired_arg = register_call.args[1]
    assert (
        isinstance(desired_arg, ast.Name) and desired_arg.id == "desired"
    ), "parent registration must pass the admitted desired state as 'desired'"

    fresh = [line for line, name in fresh_assignments if name == connection_name]
    assert len(fresh) == 1, (
        "the registration connection must be assigned exactly once from "
        "session.open_fresh_attested_connection()"
    )
    fresh_line = fresh[0]
    assert fresh_line < register_call.lineno, (
        "the fresh session-factory assignment must precede " "_register_task90_parents"
    )

    assert reconcile_calls, "the live proof must call reconciler.reconcile(...)"
    for _line, reconcile_call in reconcile_calls:
        receiver = reconcile_call.func.value
        assert (
            isinstance(receiver, ast.Name) and receiver.id == "reconciler"
        ), "every reconcile call must be the real reconciler.reconcile(...)"

    register_line = register_call.lineno
    assert register_line < min(
        line for line, _ in reconcile_calls
    ), "parent registration must run before the first reconcile"

    finally_closed: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Try):
            continue
        for statement in node.finalbody:
            for call in ast.walk(statement):
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == "_close_quietly"
                    and call.args
                    and isinstance(call.args[0], ast.Name)
                ):
                    finally_closed.add(call.args[0].id)
    assert (
        connection_name in finally_closed
    ), "the fresh registration connection must be closed in the finally block"


def _verify_support_source(source: str) -> None:
    """Source-level pins for the Task #90 binding/serializer support module.

    The module owns the process-local structural binding and the redacted
    artifact serializer, so it must reference the runtime
    ``dataclasses.fields`` digest derivation, the exact production result
    type, the single-use build token, the redacted artifact dict, and the
    canonical digest surface; and must never contain environment/secret
    access, database/Docker imports, session construction, mock/fake
    machinery, unsafe dynamic imports, exec/eval, subprocess, or the
    protected historical runner.
    """
    for required in _REQUIRED_SUPPORT_SOURCE_FRAGMENTS:
        assert required in source, f"the support module must reference {required!r}"
    for forbidden in _FORBIDDEN_SUPPORT_FRAGMENTS:
        assert (
            forbidden not in source
        ), f"the support module must not contain {forbidden!r}"


def _build_env_fixture_with_extra_read(extra_read: str, preamble: str = "") -> str:
    """Source of a ``_sanitized_env``-shaped AST fixture plus one extra read.

    The fixture is only ever parsed, never executed, and never opens a
    session.
    """
    allowlist_reads = "\n".join(
        f'        ("{key}", os.getenv("{key}")),' for key in _SANITIZED_ALLOWLIST
    )
    preamble_block = f"    {preamble}\n" if preamble else ""
    return (
        "def _sanitized_env() -> dict[str, str]:\n"
        "    env: dict[str, str] = {}\n"
        f"{preamble_block}"
        "    for key, value in (\n"
        f"{allowlist_reads}\n"
        f"        {extra_read},\n"
        "    ):\n"
        "        if value is not None:\n"
        "            env[key] = value\n"
        "    return env\n"
    )


def _live_acceptance_fixture(
    *,
    omit_auth: bool = False,
    session_open_assignment: bool = False,
    second_helper_call: bool = False,
    hardcoded_session_value: bool = False,
    omitted_assertion_field: str | None = None,
) -> str:
    """Source of a live-test-shaped AST fixture with exactly one deviation.

    The baseline fixture mirrors the approved Task #90 live test body (auth
    first, one ExitStack/session, one direct positional helper call, one
    redacted failure raise, one success assertion per required observation
    field). Each flag introduces exactly one malicious deviation. The
    fixture is only ever parsed, never executed, and never opens a session.
    """
    lines = ["def test_task90_authorized_live_acceptance():"]
    if not omit_auth:
        lines.append("    _require_authorization()")
    lines.append("    with contextlib.ExitStack() as stack:")
    lines.append("        session = DisposableE2aSession(")
    if hardcoded_session_value:
        lines.append('            container_name="hardcoded-name",')
    else:
        lines.append(
            "            container_name="
            "_validate_container_name(_generate_safe_container_name()),"
        )
    lines.append("            port=_select_ephemeral_port(),")
    lines.append("            password=_generate_test_password(),")
    lines.append("        )")
    lines.append("        stack.enter_context(session)")
    if session_open_assignment:
        lines.append("        conn = session.open_fresh_attested_connection()")
    lines.append("        observations = _run_task90_live_proof(session)")
    if second_helper_call:
        lines.append("        observations = _run_task90_live_proof(session)")
    lines.append("    if not observations.success:")
    lines.append("        raise RuntimeError(")
    lines.append(
        '            f"Task #90 acceptance cell failed: '
        '{observations.error_reason}")'
    )
    for field in sorted(REQUIRED_OBSERVATION_FIELDS):
        if omitted_assertion_field is not None and field == omitted_assertion_field:
            continue
        lines.append(f"    assert observations.{field}")
    return "\n".join(lines) + "\n"


def _task90_registration_pin_fixture(
    *,
    stale_connection_source: bool = False,
    fake_reconcile_receiver: bool = False,
    second_register_call: bool = False,
    fresh_assignment_after_registration: bool = False,
) -> str:
    """Source of a Task #90 live-proof-shaped AST fixture with deviations.

    The baseline fixture mirrors the approved ``_run_task90_live_proof``
    registration/cleanup skeleton: one fresh
    ``conn_parents = session.open_fresh_attested_connection()`` assignment,
    exactly one ``_register_task90_parents(conn_parents, desired)`` call
    BEFORE the first real ``reconciler.reconcile(...)``, and a
    ``_close_quietly(conn_parents)`` in the ``finally`` block. Each flag
    introduces exactly one malicious deviation. The fixture is only ever
    parsed, never executed, and never opens a session.

    ``fresh_assignment_after_registration`` models the ordering attack: the
    registration variable is initially bound to a stale non-session source and
    the direct session-factory assignment appears only AFTER the registration
    call, so the fresh-source pin must reject it on ordering grounds.
    """
    fresh_source = "conn_parents = session.open_fresh_attested_connection()"
    if stale_connection_source or fresh_assignment_after_registration:
        fresh_source = "conn_parents = previous_conn"
    receiver = "reconciler" if not fake_reconcile_receiver else "fake_reconcile"
    extra_register = (
        "\n        _register_task90_parents(conn_parents, desired)"
        if second_register_call
        else ""
    )
    late_fresh_assignment = (
        "\n        conn_parents = session.open_fresh_attested_connection()"
        if fresh_assignment_after_registration
        else ""
    )
    return (
        "def _run_task90_live_proof(session: Any) -> Task90Observations:\n"
        "    conn_parents = None\n"
        "    try:\n"
        f"        {fresh_source}\n"
        "        _register_task90_parents(conn_parents, desired)\n"
        f"{extra_register}\n"
        f"{late_fresh_assignment}\n"
        "        _close_quietly(conn_parents)\n"
        "        conn_parents = None\n"
        "        reconciler = E2aReconciler()\n"
        "        conn_first = session.open_fresh_attested_connection()\n"
        f"        first_result = {receiver}.reconcile(conn_first, desired)\n"
        "        return Task90Observations()\n"
        "    except Exception:\n"
        "        return _failure_observations()\n"
        "    finally:\n"
        "        _close_quietly(conn_parents)\n"
    )


__all__ = [
    "LIVE_TEST_NAME",
    "METADATA_TEST_NAME",
    "HELPER_IMPL_FUNCTION",
    "LIVE_SELECTOR_FILENAME",
    "LIVE_CELLS_FILENAME",
    "SUPPORT_FILENAME",
    "TYPES_FILENAME",
    "_SANITIZED_ALLOWLIST",
    "_SENSITIVE_ENV_VARS",
    "_single_function_by_name",
    "_verify_sanitized_env_structure",
    "_verify_live_acceptance_body",
    "_verify_live_cells_source",
    "_verify_task90_parent_registration_pin",
    "_verify_support_source",
    "_build_env_fixture_with_extra_read",
    "_live_acceptance_fixture",
    "_task90_registration_pin_fixture",
]
