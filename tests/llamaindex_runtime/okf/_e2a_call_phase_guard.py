"""Private Track-A pytest plugin: prove each collected module reached a call phase.

Loaded explicitly by the child pytest subprocess via ``-p okf._e2a_call_phase_guard``.
Tracks which modules had at least one ``pytest_runtest_call`` hook fire. At session
finish, if any collected module lacked a call phase, forces a nonzero exit status.

This plugin writes nothing to disk, outputs no raw data, inspects no source, and
hands no arbitrary input to the parent process. The parent observes only the
child return code.
"""

from __future__ import annotations

from pathlib import Path

_collected_modules: set[str] = set()
_called_modules: set[str] = set()


def _module_key(fspath: object) -> str:
    return str(Path(str(fspath)).resolve())


def pytest_collection_modifyitems(config, items):  # noqa: ANN001
    for item in items:
        _collected_modules.add(_module_key(item.fspath))


def pytest_runtest_call(item):  # noqa: ANN001
    _called_modules.add(_module_key(item.fspath))


def pytest_sessionfinish(session, exitstatus):  # noqa: ANN001
    # Collect-only sessions never invoke call phases; skip enforcement so the
    # plugin is safe to load during both collection and execution subprocesses.
    if getattr(session.config.option, "collectonly", False):
        return
    if exitstatus == 0 and _collected_modules and _called_modules < _collected_modules:
        session.exitstatus = 1
