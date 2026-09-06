"""Shared AST proof utilities for the Task #89 global acceptance proof.

Non-collected (underscore prefix) support for
``test_phase15_e2a_task89_global_acceptance_proof``: pure ``ast`` shape
verifiers and parsed-only fixture builders for the selected live
acceptance test, the sanitized-env builder, and the live cells helper
source.

This helper NEVER creates a session, NEVER accesses environment
variables, NEVER accesses a database or Docker, and NEVER alters default
pytest collection behavior (the ``_`` prefix keeps it out of default
collection). It only parses source text and inspects ASTs; fixtures built
here are parsed only, never executed.
"""

from __future__ import annotations

import ast

from ._phase15_e2a_task89_types import REQUIRED_OBSERVATION_FIELDS

LIVE_TEST_NAME = "test_task89_authorized_live_acceptance"
METADATA_TEST_NAME = "test_task89_global_acceptance_metadata"
HELPER_IMPL_FUNCTION = "_run_task89_durable_integration_impl"
LIVE_SELECTOR_FILENAME = "phase15_e2a_task89_live_acceptance.py"
LIVE_CELLS_FILENAME = "_phase15_e2a_task89_live_cells.py"
SUPPORT_FILENAME = "_phase15_e2a_task89_support.py"

# Shell-hygiene variable set: never read, never passed to child processes.
_SENSITIVE_ENV_VARS = frozenset(
    {
        "DATABASE_URL",
        "FORMAL_RUNTIME_DATABASE_URL",
        "OKF_MIGRATION_TEST_DATABASE_DISPOSABLE",
        "OKF_REBUILD_EXPECTED_DATABASE",
        "OKF_FAILURE_AUDIT_ACCEPTANCE",
        "OKF_REBUILD_DOCKER_ACCEPTANCE",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGSYSCONFDIR",
        "PGHOST",
        "PGPORT",
        "PGUSER",
        "PGPASSWORD",
        "PGDATABASE",
        "OKF_E2A_DISPOSABLE_TEST_AUTHORIZED",
    }
)

# Explicit allowlist of non-sensitive runtime keys read individually.
# PATH is universal; the Windows entries apply only when present.
_SANITIZED_ALLOWLIST = (
    "PATH",
    "HOME",
    "SystemRoot",
    "PATHEXT",
    "WINDIR",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "COMSPEC",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
)

# Fragments the Task #89 live helper source MUST reference (real production
# boundaries of the durable-integration composed proof).
_REQUIRED_HELPER_SOURCE_FRAGMENTS = (
    "llamaindex_runtime.ingestion.pipeline",
    "llamaindex_runtime.ingestion.docling_ingestor",
    "llamaindex_runtime.okf.e2a_reconciler",
    "llamaindex_runtime.registry.postgres_adapter",
    "llamaindex_runtime.tree.pageindex_adapter",
    "_deterministic_embedding",
    "_make_counting_wrapper",
)

# Fragments the Task #89 live cells module MUST reference (real production
# boundaries of the durable-integration composed proof, the scoped-restore
# instrumentation mechanism, and the factory-connection lifecycle).
_REQUIRED_HELPER_BODY_FRAGMENTS = (
    "pipeline.ingest(",
    "admit_e2a_materialization_input",
    "serialize_document",
    "publish_raw_pair",
    "E2aDesiredStateBuilder",
    "PostgresRegistryWriter",
    "DoclingIngestor",
    "E2aReconciler",
    "retrieve_tree_hits",
    "index_tree",
    "_flatten_embedded_tree",
    "ExitStack",
    "_AttributeSwap",
    "factory_state",
)

# Fake/replacement machinery that must NEVER appear in the live helper.
_FORBIDDEN_HELPER_FRAGMENTS = (
    "unittest.mock",
    "MagicMock",
    "monkeypatch",
    "create_autospec",
    "patch(",
    "NotImplementedError",
)

# Environment/Docker/session/secret hygiene for the live cells module.
_FORBIDDEN_MODULE_FRAGMENTS = (
    "os.environ",
    "getenv",
    "DATABASE_URL",
    "PGHOST",
    "PGUSER",
    "PGPASSWORD",
    "OPENAI_API_KEY",
    "import pytest",
    "pytest.",
    "skip(",
    "xfail(",
    "unittest.mock",
    "MagicMock",
    "monkeypatch",
    "create_autospec",
    "DisposableE2aSession(",
)

# Fragments the Task #89 support module MUST reference: the explicit-file
# spec loading surface, the unique scoped module key, the BaseException
# restore path, the real Docling reader/node-parser loader path, and the
# bounded class/type-only diagnostic.
_REQUIRED_SUPPORT_SOURCE_FRAGMENTS = (
    "spec_from_file_location",
    "run_e2a_verification.py",
    "_VERIFICATION_MODULE_NAME",
    "except BaseException",
    "_restore_sys_modules_key",
    "load_docling_reader_class",
    "load_docling_node_parser_class",
    "error_type[:64]",
)

# Fake/replacement machinery, environment/secret access, sys.path
# mutation, session/DB construction, and unsafe dynamic-import or
# exec/eval calls that must NEVER appear in the support module source.
_FORBIDDEN_SUPPORT_FRAGMENTS = (
    "os.environ",
    "getenv",
    "DATABASE_URL",
    "PGHOST",
    "PGUSER",
    "PGPASSWORD",
    "OPENAI_API_KEY",
    "import pytest",
    "pytest.",
    "unittest.mock",
    "MagicMock",
    "monkeypatch",
    "create_autospec",
    "patch(",
    "sys.path.insert",
    "sys.path.append",
    "sys.path[",
    "sys.path =",
    "DisposableE2aSession(",
    "open_fresh_attested_connection",
    "__import__",
    "importlib.import_module",
    "exec(",
    "eval(",
    "compile(",
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
    """True only for the direct zero-keyword ``os.getenv(<one arg>)`` form.

    The callee must be the literal attribute access ``os.getenv`` (an
    ``ast.Attribute`` on the plain name ``os``), with no keyword
    arguments and exactly one positional argument. Indirect forms such as
    ``getattr(os, "getenv")(...)``, aliased imports, or subscript
    indirection are all structurally not this shape.
    """
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

    Accepts ONLY direct zero-keyword ``os.getenv("<literal key>")``
    calls: every call inside the builder must be exactly that shape with
    a single literal string argument, and every attribute access
    anywhere in the builder must be exactly the direct ``os.getenv``
    form. The collected literal keys must equal the allowlist exactly and
    stay disjoint from the sensitive variable names.
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
      (a zero-argument ``_generate_safe_container_name()`` call nested in a
      one-argument ``_validate_container_name(...)`` call),
    - ``port=_select_ephemeral_port()`` (a zero-argument call),
    - ``password=_generate_test_password()`` (a zero-argument call).

    Any hardcoded literal, substituted name, injected environment read, or
    otherwise altered value expression fails here.
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
      (keyword-only, no positional arguments), with every keyword bound to
      EXACTLY the approved safe value expression, enters it exactly once
      via ``stack.enter_context(session)``, and invokes
      ``_run_task89_durable_integration_impl(session)`` exactly once as a
      direct positional call with only the session argument,
    - exactly one ``if not observations.success:`` failure raise:
      ``RuntimeError`` whose message interpolates ONLY
      ``observations.error_reason`` after a fixed prefix,
    - exactly 25 success assertions, each of the form
      ``assert observations.<field>``, covering every required
      observation field exactly once.

    The live test must never call ``session.open_fresh_attested_connection``
    itself. Any extra statement, assignment-wrapped or session-attribute
    call, altered argument, hardcoded or substituted session value, second
    helper call, missing authorization, or missing assertion fails here.
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
    ), "the live test must invoke _run_task89_durable_integration_impl exactly once"
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
    assert (
        len(assertions) == 25
    ), "the live test must make exactly 25 success assertions"
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
    """Source-level pins for the Task #89 live cells module.

    The module must reference every real production boundary fragment,
    contain the core helper, and never contain environment reads, secret
    names, session construction, or fake/replacement machinery.
    """
    for required in _REQUIRED_HELPER_SOURCE_FRAGMENTS:
        assert required in source, f"live cells must reference {required!r}"
    for forbidden in _FORBIDDEN_MODULE_FRAGMENTS:
        assert forbidden not in source, f"live cells must not contain {forbidden!r}"


def _verify_live_cells_boundaries(source: str) -> None:
    """Source-level pins for the Task #89 live cells module.

    The module must reference every real production boundary fragment
    (pipeline, ingestor, serializer/publisher/admission, reconciler/builder,
    registry writer, PageIndex adapter), the scoped-restore instrumentation
    mechanism (``ExitStack`` + ``_AttributeSwap``), and the factory-connection
    lifecycle (``factory_state``), and never contain environment reads, secret
    names, session construction, or fake/replacement machinery. Because the
    live helper is deliberately split into named stage helpers, the boundary
    references are validated across the whole module rather than one
    monolithic body.
    """
    for required in _REQUIRED_HELPER_BODY_FRAGMENTS:
        assert required in source, f"the live cells module must reference {required!r}"
    for forbidden in _FORBIDDEN_HELPER_FRAGMENTS:
        assert (
            forbidden not in source
        ), f"the live cells module must not contain {forbidden!r}"


def _verify_support_source(source: str) -> None:
    """Source-level pins for the Task #89 support module.

    The module owns the file-based verification-module loader and the real
    Docling ingestor constructor, so it must reference the explicit-file
    spec loading surface (``run_e2a_verification.py``), the unique scoped
    ``sys.modules`` key, the ``BaseException`` restore path, the real
    reader/node-parser loader path, and the bounded class/type-only
    diagnostic; and must never contain environment/secret access,
    mock/fake machinery, sys.path mutation, session/DB construction, or
    unsafe dynamic imports or exec/eval.
    """
    for required in _REQUIRED_SUPPORT_SOURCE_FRAGMENTS:
        assert required in source, f"the support module must reference {required!r}"
    for forbidden in _FORBIDDEN_SUPPORT_FRAGMENTS:
        assert (
            forbidden not in source
        ), f"the support module must not contain {forbidden!r}"


def _references_factory_state(node: ast.AST) -> bool:
    """True when an AST subtree references the ``factory_state`` local."""
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name) and node.value.id == "factory_state":
            return True
        return _references_factory_state(node.value)
    if isinstance(node, ast.Call):
        return _references_factory_state(node.func)
    return False


def _verify_helper_finally_closes_factory(function: ast.FunctionDef) -> None:
    """Structural proof: the live helper's finally closes the factory connection.

    The core helper's ``finally`` block must call ``_close_quietly`` with an
    argument that references ``factory_state`` (e.g.
    ``_close_quietly(factory_state.get("connection"))``). This guards against
    leaking the reconciler primary connection when ``E2aReconciler.reconcile``
    raises in ``_require_manual_transaction`` or in the builder pre-stages,
    before its own internal try/cleanup would ever run.
    """
    finally_blocks = [
        node.finalbody
        for node in ast.walk(function)
        if isinstance(node, ast.Try) and node.finalbody
    ]
    assert finally_blocks, "the live helper must have a finally block"
    for block in finally_blocks:
        block_module = ast.Module(body=list(block), type_ignores=[])
        close_calls = [
            node
            for node in ast.walk(block_module)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_close_quietly"
        ]
        assert any(
            any(_references_factory_state(argument) for argument in close_call.args)
            for close_call in close_calls
        ), "the helper finally must close the factory connection"


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
) -> str:
    """Source of a live-test-shaped AST fixture with exactly one deviation.

    The baseline fixture mirrors the approved Task #89 live test body (auth
    first, one ExitStack/session, one direct positional helper call, one
    redacted failure raise, 25 success assertions). Each flag introduces
    exactly one malicious deviation. The fixture is only ever parsed,
    never executed, and never opens a session.
    """
    lines = ["def test_task89_authorized_live_acceptance():"]
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
    lines.append("        observations = _run_task89_durable_integration_impl(session)")
    if second_helper_call:
        lines.append(
            "        observations = _run_task89_durable_integration_impl(session)"
        )
    lines.append("    if not observations.success:")
    lines.append("        raise RuntimeError(")
    lines.append(
        '            f"Task #89 global acceptance cell failed: '
        '{observations.error_reason}")'
    )
    for field in sorted(REQUIRED_OBSERVATION_FIELDS):
        lines.append(f"    assert observations.{field}")
    return "\n".join(lines) + "\n"
