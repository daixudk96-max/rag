"""Regression test for Task #87: _observe_container_presence must filter by name.

Guards the minimal #87 repair: the `docker ps -a` observation command
must pass an adjacent literal `--filter name=<validated-name>` pair so
that unrelated daemon containers cannot cause the EXACT parser to emit
`ambiguous_output` (which `_startup_impl` maps to the false
"container already exists" failure).

Security contract under test:
- Only the VALIDATED name may enter the docker argv.
- The filter value is a literal (no regex anchors / prefix-suffix
  operators). The filter narrows the candidate set only.
- The EXACT output parser remains final authority: any record that is
  not the exact validated name + 64-hex ID fails closed as
  ambiguous_output. A filter mismatch is NEVER relaxed into absence.
"""

from __future__ import annotations

from typing import Any, Sequence
from unittest.mock import MagicMock

from ._phase15_e2a_harness_lifecycle import _observe_container_presence


class TestTask87NameFilterRegression:
    """Regression tests for docker ps --filter name=<validated_name>."""

    def test_uses_literal_name_filter_to_reduce_ambiguity(self) -> None:
        """docker ps -a argv must contain adjacent literal --filter name=<name>.

        Without this filter, docker ps -a returns ALL containers in the
        daemon, so unrelated records make the EXACT parser emit
        ambiguous_output (mapped to "container already exists").
        """
        docker_args_list: list[list[str]] = []

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            docker_args_list.append(list(args))
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result

        test_name = "test-container-name-filter"
        _observe_container_presence(test_name, config_dir="/tmp/config", run=mock_run)

        # Exactly one docker invocation: the ps -a observation command.
        assert len(docker_args_list) == 1
        ps_args = docker_args_list[0]
        assert "ps" in ps_args
        assert "-a" in ps_args

        # Adjacent literal --filter / name=<validated-name> pair.
        assert "--filter" in ps_args, "docker ps -a must include --filter"
        filter_index = ps_args.index("--filter")
        assert filter_index + 1 < len(ps_args), "--filter must have a value"
        filter_value = ps_args[filter_index + 1]
        # No regex anchors or Docker prefix/suffix operators.
        assert "name=^" not in filter_value, "Filter must not use regex anchors"
        assert "name=$" not in filter_value, "Filter must not use regex anchors"
        # The value must be the exact validated literal name.
        assert (
            filter_value == f"name={test_name}"
        ), f"Filter must be name={test_name}, got {filter_value!r}"

    def test_invalid_name_never_reaches_docker_argv(self) -> None:
        """Only VALIDATED names may enter the docker argv."""
        docker_args_list: list[list[str]] = []

        def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
            docker_args_list.append(list(args))
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result

        result = _observe_container_presence(
            "--help", config_dir="/tmp/config", run=mock_run
        )
        assert result.status == "inspection_failure"
        assert docker_args_list == [], "Docker must not run for an invalid name"

    def test_exact_output_parsing_remains_final_authority(self) -> None:
        """The filter narrows input; the EXACT parser still decides.

        Even with the literal name filter present in argv, any stdout
        record that is not the exact validated name + 64-hex ID must
        fail closed as ambiguous_output. Inspection failures and
        ambiguities are never relaxed into absence.
        """
        container_id = "a" * 64
        observed_filter: list[str] = []

        def make_runner(stdout: str) -> Any:
            def mock_run(args: Sequence[str], **kwargs: Any) -> MagicMock:
                for i, arg in enumerate(args):
                    if arg == "--filter" and i + 1 < len(args):
                        observed_filter.append(args[i + 1])
                result = MagicMock()
                result.returncode = 0
                result.stdout = stdout
                return result

            return mock_run

        # (a) Wrong-name record: rejected even though the filter was
        #     correctly applied.
        observed_filter.clear()
        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=make_runner(f"test-container-extra\t{container_id}\n"),
        )
        assert observed_filter == ["name=test-container"]
        assert (
            result.status == "ambiguous_output"
        ), "Wrong-name record must fail closed even with a name filter"

        # (b) Multiple records: still ambiguous, never guessed.
        observed_filter.clear()
        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=make_runner(
                f"test-container\t{container_id}\n"
                f"test-container-extra\t{'b' * 64}\n"
            ),
        )
        assert observed_filter == ["name=test-container"]
        assert (
            result.status == "ambiguous_output"
        ), "Multiple records must fail closed even with a name filter"

        # (c) Exact single record: the only path to present.
        observed_filter.clear()
        result = _observe_container_presence(
            "test-container",
            config_dir="/tmp/config",
            run=make_runner(f"test-container\t{container_id}\n"),
        )
        assert observed_filter == ["name=test-container"]
        assert result.status == "present"
        assert result.container_id == container_id
