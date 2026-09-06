"""Focused AST/SQL verifier for the Task #89 durable observer.

Non-collected (underscore prefix) support shared by the Task #89 contract
suites. This module owns exactly one concern split out of
``_phase15_e2a_task89_ast_proof`` so every Task #89 file stays under the
project <800 physical-line limit: the structural proof of
``_verify_observer_durable``'s version-scoped durability SQL.

The verifier parses the supplied module source with ``ast``, locates the
``_verify_observer_durable`` function, resolves the first ``cursor.execute``
argument for every execute call (``ast.Constant`` strings -- implicit
adjacent-literal concatenation is already merged by the parser -- plus
simple module-level ``NAME = "<string>"`` references), normalizes SQL
whitespace, and then proves:

- direct parameterized version COUNTs for ``canonical_spans`` and
  ``vector_chunks``,
- exactly one ``vector_chunk_spans`` COUNT that structurally JOINs
  ``vector_chunks`` on an explicit equality of the two ``chunk_id``
  references (either operand order; alias renames and optional
  ``AS``/whitespace variation allowed) and filters ``version_id`` through
  the ``vector_chunks`` alias,
- no direct/unjoined ``vector_chunk_spans ... WHERE [alias.]version_id``
  variant (the recorded ``UndefinedColumn`` root cause).

The verifier fails closed: every direct ``cursor.execute`` inside
``_verify_observer_durable`` must receive a first argument that resolves to
SQL text (a harmless constant extraction or an adjacent-literal split cannot
evade the guard; f-strings, unresolved names, and unknown ``+`` BinOps
raise), and any malformed required query raises instead of passing
vacuously. A ``"prefix" + loop_var`` BinOp over a literal tuple/list of
strings (the live cells global-table loop) resolves to one statement per
iterated value.

This helper NEVER creates a session, NEVER accesses environment
variables, NEVER accesses a database or Docker, and NEVER alters default
pytest collection behavior (the ``_`` prefix keeps it out of default
collection). It only parses source text and inspects ASTs.
"""

from __future__ import annotations

import ast
import re

from ._phase15_e2a_task89_ast_proof import _single_function_by_name

OBSERVER_DURABLE_FUNCTION = "_verify_observer_durable"


def _module_level_string_constants(tree: ast.Module) -> dict[str, str]:
    """Map plain module-level ``NAME = "<string>"`` assignments."""
    constants: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            constants[node.targets[0].id] = node.value.value
    return constants


def _loop_string_values(function: ast.FunctionDef) -> dict[str, tuple[str, ...]]:
    """Map for-loop targets iterating a literal tuple/list of strings.

    Used to resolve ``cursor.execute("prefix" + loop_var)`` shapes (the live
    cells global-table loop) so the fail-closed resolution rule does not
    reject a resolvable loop-carried count.
    """
    values: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(function):
        if not isinstance(node, ast.For) or not isinstance(node.target, ast.Name):
            continue
        elements = (
            node.iter.elts if isinstance(node.iter, (ast.Tuple, ast.List)) else ()
        )
        if elements and all(
            isinstance(e, ast.Constant) and isinstance(e.value, str) for e in elements
        ):
            values[node.target.id] = tuple(e.value for e in elements)
    return values


def _resolve_execute_sql(
    argument: ast.AST,
    module_constants: dict[str, str],
    loop_values: dict[str, tuple[str, ...]],
) -> list[str]:
    """Resolve a cursor.execute first argument to its SQL text(s).

    ``ast.Constant`` strings (implicit adjacent-literal concatenation is
    already merged by the parser) resolve directly; a simple module-level
    ``NAME = "<string>"`` reference resolves through the constant map; a
    constant ``+`` constant BinOp folds; a constant ``+`` loop-name BinOp
    expands to one statement per iterated value. Anything else (f-strings,
    unresolved names, unknown BinOps) is unresolvable and returns an empty
    list so the caller fails closed.
    """
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return [argument.value]
    if isinstance(argument, ast.Name):
        resolved = module_constants.get(argument.id)
        return [resolved] if resolved is not None else []
    if isinstance(argument, ast.BinOp) and isinstance(argument.op, ast.Add):
        left = argument.left
        right = argument.right
        left_is_const = isinstance(left, ast.Constant) and isinstance(left.value, str)
        right_is_const = isinstance(right, ast.Constant) and isinstance(
            right.value, str
        )
        if left_is_const and right_is_const:
            return [left.value + right.value]
        if left_is_const and isinstance(right, ast.Name):
            looped = loop_values.get(right.id)
            if looped is not None:
                return [left.value + value for value in looped]
    return []


def _execute_sql_statements(
    function: ast.FunctionDef,
    module_constants: dict[str, str],
    loop_values: dict[str, tuple[str, ...]],
) -> list[str]:
    """Collect the resolved SQL of every direct ``cursor.execute`` call.

    Fail-closed: every direct ``cursor.execute`` must receive a first
    argument that resolves to SQL text, otherwise verification raises. No
    unresolved execute is silently dropped.
    """
    statements: list[str] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "execute"):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "cursor"):
            continue
        if not node.args:
            raise AssertionError(
                "every direct cursor.execute must receive a SQL first argument"
            )
        resolved = _resolve_execute_sql(node.args[0], module_constants, loop_values)
        if not resolved:
            raise AssertionError(
                "every direct cursor.execute first argument must resolve to SQL text"
            )
        statements.extend(resolved)
    return statements


def _normalize_sql_whitespace(sql: str) -> str:
    """Collapse every run of SQL whitespace to a single space."""
    return " ".join(sql.split())


def _count_query_table(sql: str) -> str | None:
    """Return the FROM table of a ``SELECT COUNT(*)`` statement, or None."""
    match = re.match(r"SELECT COUNT\(\*\) FROM (\w+)", _normalize_sql_whitespace(sql))
    return match.group(1) if match else None


def _is_direct_version_count(sql: str, table: str) -> bool:
    """True only for a direct parameterized version COUNT on ``table``.

    The COUNT must select straight from ``table`` with no JOIN and a
    parameterized ``version_id`` filter (optionally table-qualified). An
    alias-renamed or joined variant is NOT a direct count.
    """
    normalized = _normalize_sql_whitespace(sql)
    if _count_query_table(normalized) != table or re.search(r"\bJOIN\b", normalized):
        return False
    return (
        re.fullmatch(
            rf"SELECT COUNT\(\*\) FROM {table}(?: AS \w+|\s+\w+)? "
            rf"WHERE (?:{table}\.)?version_id = %s",
            normalized,
        )
        is not None
    )


def _verify_vector_chunk_spans_join(sql: str) -> None:
    """Structural proof that a vector_chunk_spans COUNT joins vector_chunks.

    Accepts alias renames and optional ``AS``/whitespace variation. The
    COUNT must JOIN ``vector_chunks`` on the two ``chunk_id`` references
    and filter ``version_id`` through the ``vector_chunks`` alias only;
    any direct/unjoined version filter (the recorded ``UndefinedColumn``
    root cause) is rejected.
    """
    normalized = _normalize_sql_whitespace(sql)
    parts = re.split(r"\s+(JOIN|ON|WHERE)\s+", normalized)
    if len(parts) != 7 or parts[1] != "JOIN" or parts[3] != "ON" or parts[5] != "WHERE":
        raise AssertionError(
            "the vector_chunk_spans COUNT must JOIN vector_chunks on the "
            "two chunk_id references and filter version_id via the "
            "vector_chunks alias"
        )
    select_from, join_clause, on_clause, where_clause = (
        parts[0],
        parts[2],
        parts[4],
        parts[6],
    )
    base = re.fullmatch(
        r"SELECT COUNT\(\*\) FROM vector_chunk_spans(?: AS (\w+)| (\w+))?",
        select_from,
    )
    joined = re.fullmatch(r"vector_chunks(?: AS (\w+)| (\w+))?", join_clause)
    if base is None or joined is None:
        raise AssertionError("the vector_chunk_spans COUNT must JOIN vector_chunks")
    base_ref = base.group(1) or base.group(2) or "vector_chunk_spans"
    join_ref = joined.group(1) or joined.group(2) or "vector_chunks"
    refs_pair = {f"{base_ref}.chunk_id", f"{join_ref}.chunk_id"}
    equalities = re.findall(
        r"([A-Za-z_]\w*\.[A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*\.[A-Za-z_]\w*)",
        on_clause,
    )
    if not any(set(pair) == refs_pair for pair in equalities):
        raise AssertionError(
            "vector_chunk_spans must JOIN vector_chunks on exactly the two "
            "chunk_id references"
        )
    if "version_id" in on_clause:
        raise AssertionError("the ON clause must not reference version_id")
    version_refs = re.findall(r"(?:\w+\.)?version_id", where_clause)
    if version_refs != [f"{join_ref}.version_id"]:
        raise AssertionError(
            "the version filter must be exactly the parameterized "
            f"{join_ref}.version_id through the vector_chunks alias"
        )
    if not re.search(rf"\b{join_ref}\.version_id\b\s*=\s*%s", where_clause):
        raise AssertionError(
            "the version filter must use the parameterized %s placeholder"
        )


def _verify_observer_durable_sql(source: str) -> None:
    """AST/SQL proof of the durable observer's version-scoped durability counts.

    Parses the supplied module source, locates ``_verify_observer_durable``,
    resolves every ``cursor.execute`` first argument, normalizes SQL
    whitespace, requires direct parameterized version COUNTs for
    ``canonical_spans`` and ``vector_chunks``, requires exactly one
    ``vector_chunk_spans`` COUNT that joins through ``vector_chunks`` on the
    two ``chunk_id`` references with the version filter through the
    ``vector_chunks`` alias, and rejects any direct/unjoined variant. The
    verifier fails closed: any unresolved or malformed required query raises
    instead of passing vacuously.
    """
    tree = ast.parse(source)
    function = _single_function_by_name(tree, OBSERVER_DURABLE_FUNCTION)
    module_constants = _module_level_string_constants(tree)
    loop_values = _loop_string_values(function)
    statements = _execute_sql_statements(function, module_constants, loop_values)
    assert statements, "no cursor.execute SQL could be resolved"
    assert any(
        _is_direct_version_count(s, "canonical_spans") for s in statements
    ), "a direct parameterized canonical_spans version COUNT is required"
    assert any(
        _is_direct_version_count(s, "vector_chunks") for s in statements
    ), "a direct parameterized vector_chunks version COUNT is required"
    vcs_statements = [
        s for s in statements if _count_query_table(s) == "vector_chunk_spans"
    ]
    assert len(vcs_statements) == 1, "exactly one vector_chunk_spans COUNT is required"
    _verify_vector_chunk_spans_join(vcs_statements[0])
