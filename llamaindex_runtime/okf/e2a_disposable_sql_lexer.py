"""Fail-closed lexical SQL comparison helpers."""

from __future__ import annotations


_ASCII_WHITESPACE = frozenset(" \t\n\r\f")


def _is_word_character(value: str) -> bool:
    return len(value) == 1 and (
        "A" <= value <= "Z"
        or "a" <= value <= "z"
        or "0" <= value <= "9"
        or value in {"_", "$"}
        or ord(value) > 0x7F
    )


def _is_ascii_whitespace(value: str) -> bool:
    return value in _ASCII_WHITESPACE


def _is_ascii_dollar_tag_start(value: str) -> bool:
    return value == "_" or "A" <= value <= "Z" or "a" <= value <= "z"


def _is_ascii_dollar_tag_continuation(value: str) -> bool:
    return _is_ascii_dollar_tag_start(value) or "0" <= value <= "9"


def _is_dollar_quote_eligible(value: str, start: int) -> bool:
    return start == 0 or not _is_word_character(value[start - 1])


def _dollar_delimiter(value: str, start: int) -> str | None:
    if start >= len(value) or value[start] != "$":
        return None
    if start + 1 < len(value) and value[start + 1] == "$":
        return "$$"
    if start + 1 >= len(value) or not _is_ascii_dollar_tag_start(value[start + 1]):
        return None
    end = start + 2
    while end < len(value) and _is_ascii_dollar_tag_continuation(value[end]):
        end += 1
    if end < len(value) and value[end] == "$":
        return value[start : end + 1]
    return None


def _is_invalid_dollar_delimiter(value: str, start: int) -> bool:
    if start + 1 >= len(value):
        return False
    character = value[start + 1]
    if ord(character) > 0x7F:
        return True
    if "0" <= character <= "9":
        return True
    if not _is_ascii_dollar_tag_start(character):
        return False
    end = start + 2
    while end < len(value) and _is_ascii_dollar_tag_continuation(value[end]):
        end += 1
    return end >= len(value) or value[end] != "$"


def _is_malformed_dollar_delimiter(value: str, start: int) -> bool:
    return _is_invalid_dollar_delimiter(value, start)


def _scan_quoted(value: str, start: int, *, escaped: bool) -> int:
    quote = value[start]
    index = start + 1
    while index < len(value):
        character = value[index]
        if escaped and character == "\\":
            if index + 1 >= len(value):
                raise ValueError("executed_failed")
            index += 2
            continue
        if character == quote:
            if index + 1 < len(value) and value[index + 1] == quote:
                index += 2
                continue
            return index + 1
        index += 1
    raise ValueError("executed_failed")


def _append_token(
    result: list[str],
    token: str,
    *,
    pending_space: bool,
    word: bool,
    comparison: bool,
) -> bool:
    if (
        pending_space
        and result
        and (not comparison or (word and _is_word_character(result[-1][-1])))
    ):
        result.append(" ")
    result.append(token)
    return False


def _definition(value: str, *, _comparison: bool = False) -> str:
    """Lexically normalize SQL without rewriting identifiers or literal content.

    The comparator is deliberately conservative: it accepts only whitespace,
    comments, and redundant whole-expression parentheses as insignificant.  It
    recognizes PostgreSQL ordinary/E/Unicode/dollar strings, quoted identifiers,
    line comments, and nested block comments; malformed input raises instead of
    being guessed at.
    """
    if type(value) is not str:
        raise ValueError("executed_failed")
    result: list[str] = []
    pending_space = False
    depth = 0
    index = 0
    while index < len(value):
        character = value[index]
        if _is_ascii_whitespace(character):
            pending_space = bool(result)
            index += 1
            continue
        if value.startswith("--", index):
            index += 2
            while index < len(value) and value[index] not in "\r\n":
                index += 1
            pending_space = bool(result)
            continue
        if value.startswith("/*", index):
            comment_depth = 1
            index += 2
            while index < len(value) and comment_depth:
                if value.startswith("/*", index):
                    comment_depth += 1
                    index += 2
                elif value.startswith("*/", index):
                    comment_depth -= 1
                    index += 2
                else:
                    index += 1
            if comment_depth:
                raise ValueError("executed_failed")
            pending_space = bool(result)
            continue
        if value.startswith("*/", index):
            raise ValueError("executed_failed")
        dollar_quote_eligible = character == "$" and _is_dollar_quote_eligible(
            value, index
        )
        delimiter = _dollar_delimiter(value, index) if dollar_quote_eligible else None
        if (
            dollar_quote_eligible
            and delimiter is None
            and _is_invalid_dollar_delimiter(value, index)
        ):
            raise ValueError("executed_failed")
        if delimiter is not None:
            end = value.find(delimiter, index + len(delimiter))
            if end < 0:
                raise ValueError("executed_failed")
            pending_space = _append_token(
                result,
                value[index : end + len(delimiter)],
                pending_space=pending_space,
                word=False,
                comparison=_comparison,
            )
            index = end + len(delimiter)
            continue
        if character in {"'", '"'}:
            escaped = (
                character == "'"
                and index > 0
                and value[index - 1] in {"E", "e"}
                and (index < 2 or not _is_word_character(value[index - 2]))
            )
            end = _scan_quoted(value, index, escaped=escaped)
            pending_space = _append_token(
                result,
                value[index:end],
                pending_space=pending_space,
                word=False,
                comparison=_comparison,
            )
            index = end
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("executed_failed")
        pending_space = _append_token(
            result,
            character,
            pending_space=pending_space,
            word=_is_word_character(character),
            comparison=_comparison,
        )
        index += 1
    if depth:
        raise ValueError("executed_failed")
    return "".join(result).strip()


def _check_definitions_match(actual: str, expected: str) -> bool:
    """Compare CHECK expressions while retaining every identifier and literal byte."""
    try:
        return _expressions_match(_check_body(actual), _check_body(expected))
    except ValueError:
        return False


def _expressions_match(actual: str, expected: str) -> bool:
    """Compare expressions modulo lexical whitespace/comments and whole wrappers."""
    try:
        return _strip_outer_parentheses(actual) == _strip_outer_parentheses(expected)
    except ValueError:
        return False


def _check_body(value: str) -> str:
    normalized = _definition(value)
    if not normalized.startswith("CHECK "):
        raise ValueError("executed_failed")
    body = normalized.removeprefix("CHECK ").strip()
    if not _is_wrapped_in_parentheses(body):
        raise ValueError("executed_failed")
    return body[1:-1].strip()


def _strip_outer_parentheses(value: str) -> str:
    normalized = _definition(value, _comparison=True)
    while _is_wrapped_in_parentheses(normalized):
        normalized = normalized[1:-1]
    return normalized


def _is_wrapped_in_parentheses(value: str) -> bool:
    if len(value) < 2 or value[0] != "(" or value[-1] != ")":
        return False
    depth = 0
    index = 0
    while index < len(value):
        character = value[index]
        delimiter = (
            _dollar_delimiter(value, index)
            if character == "$" and _is_dollar_quote_eligible(value, index)
            else None
        )
        if delimiter is not None:
            end = value.find(delimiter, index + len(delimiter))
            if end < 0:
                raise ValueError("executed_failed")
            index = end + len(delimiter)
            continue
        if character in {"'", '"'}:
            escaped = (
                character == "'"
                and index > 0
                and value[index - 1] in {"E", "e"}
                and (index < 2 or not _is_word_character(value[index - 2]))
            )
            index = _scan_quoted(value, index, escaped=escaped)
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index == len(value) - 1
            if depth < 0:
                raise ValueError("executed_failed")
        index += 1
    raise ValueError("executed_failed")


def _fk(columns: str, target: str, target_columns: str) -> str:
    return _definition(
        f"FOREIGN KEY ({columns}) REFERENCES {target}({target_columns}) ON DELETE RESTRICT"
    )


def _unique(columns: str) -> str:
    return _definition(f"UNIQUE ({columns})")


def _check(expression: str) -> str:
    return _definition(f"CHECK ({expression})")
