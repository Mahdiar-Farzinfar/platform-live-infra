#!/usr/bin/env python3
"""Build a deterministic plan matrix from detect-changed-stacks JSON.

Input: --changed-stacks FILE (or - for UTF-8 stdin), containing exactly
{"stacks": ["live/path/to/stack", ...]}. The paths are repository-relative
directories, not terragrunt.hcl filenames. Output on stdout is one JSON object:
{"matrix": {"include": [{"stack_id": ..., "path": ..., "phase": ...,
"wave": ..., "depends_on": [...], "owners": [...]}, ...]}}.

Entries follow inventory/deployment-order.yaml phase/wave/stack order. An empty
selection produces {"matrix":{"include":[]}}. This command only selects plan
targets. Dependencies remain listed even when they are not changed; this
command does not expand the selection, authorize, or schedule an apply.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:
    raise SystemExit(
        "build-plan-matrix: PyYAML is required; install docs/requirements.txt"
    ) from exc


class MatrixError(Exception):
    """Invalid input or repository inventory."""


MAX_INPUT_BYTES = 1024 * 1024


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects silently overwritten mapping keys."""


def unique_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode) -> dict:
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str):
            raise MatrixError(
                f"YAML mapping key must be a string at line {key_node.start_mark.line + 1}"
            )
        if key in result:
            raise MatrixError(f"duplicate YAML key {key!r} at line {key_node.start_mark.line + 1}")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping
)


def mapping(value: object, where: str) -> dict:
    if not isinstance(value, dict):
        raise MatrixError(f"{where}: expected a mapping")
    return value


def sequence(value: object, where: str) -> list:
    if not isinstance(value, list):
        raise MatrixError(f"{where}: expected a list")
    return value


def nonempty(value: object, where: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value or any(
        ord(char) < 32 for char in value
    ):
        raise MatrixError(
            f"{where}: expected a nonempty string without surrounding whitespace or controls"
        )
    return value


def string_list(value: object, where: str, *, allow_empty: bool = True) -> list[str]:
    items = sequence(value, where)
    if not allow_empty and not items:
        raise MatrixError(f"{where}: list must not be empty")
    result = [nonempty(item, f"{where}[{index}]") for index, item in enumerate(items)]
    if len(result) != len(set(result)):
        raise MatrixError(f"{where}: duplicate entries")
    return result


def stack_path(value: object, where: str) -> str:
    name = nonempty(value, where)
    if (
        not name.startswith("live/")
        or "\\" in name
        or ":" in name
        or any(part in ("", ".", "..") for part in name.split("/"))
    ):
        raise MatrixError(
            f"{where}: expected a normalized live/ repository-relative "
            f"stack directory, got {name!r}"
        )
    return name


def load_yaml(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = yaml.load(stream, Loader=UniqueKeyLoader)
    except MatrixError as exc:
        raise MatrixError(f"{path}: {exc}") from exc
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise MatrixError(f"{path}: cannot read YAML: {exc}") from exc
    return mapping(value, str(path))


def require_version(document: dict, path: Path) -> None:
    if type(document.get("version")) is not int or document["version"] != 1:
        raise MatrixError(f"{path}: unsupported or missing inventory version (expected 1)")


def discover_stacks(root: Path) -> set[str]:
    live = root / "live"
    if not live.is_dir():
        raise MatrixError(f"{live}: live directory does not exist")
    stacks = set()

    def fail_walk(error: OSError) -> None:
        raise error

    for directory, children, files in os.walk(live, onerror=fail_walk):
        children[:] = sorted(child for child in children if child not in (
            ".terraform", ".terragrunt-cache"
        ))
        current = Path(directory)
        if current != live and "terragrunt.hcl" in files:
            if not (current / "terragrunt.hcl").is_symlink():
                stacks.add(current.relative_to(root).as_posix())
    for path in sorted(stacks):
        if any(path.startswith(other + "/") for other in stacks if other != path):
            raise MatrixError(f"{live}: nested Terragrunt stacks are ambiguous: {path}")
    return stacks


def inventory_entries(root: Path) -> list[dict]:
    order_path = root / "inventory" / "deployment-order.yaml"
    owners_path = root / "inventory" / "stack-owners.yaml"
    order = load_yaml(order_path)
    owners_doc = load_yaml(owners_path)
    require_version(order, order_path)
    require_version(owners_doc, owners_path)

    repo = mapping(order.get("repository"), f"{order_path}: repository")
    if repo.get("live_root") != "live":
        raise MatrixError(f"{order_path}: repository.live_root must be 'live'")
    discovery = mapping(repo.get("stack_discovery"), f"{order_path}: repository.stack_discovery")
    if (discovery.get("identifier") != "stack_id"
            or discovery.get("include") != "live/**/terragrunt.hcl"
            or discovery.get("exclude") != ["live/terragrunt.hcl"]):
        raise MatrixError(f"{order_path}: unsupported repository.stack_discovery settings")

    owners: dict[str, list[str]] = {}
    for index, raw in enumerate(sequence(owners_doc.get("stacks"), f"{owners_path}: stacks")):
        where = f"{owners_path}: stacks[{index}]"
        record = mapping(raw, where)
        path = stack_path(record.get("path"), f"{where}.path")
        if path in owners:
            raise MatrixError(f"{where}: duplicate owner entry for {path}")
        owners[path] = string_list(record.get("owners"), f"{where}.owners", allow_empty=False)

    phases: dict[str, tuple[int, dict[str, int]]] = {}
    wave_positions: dict[str, tuple[int, int, int]] = {}
    wave_ids: set[str] = set()
    phase_orders: set[int] = set()
    for phase_index, raw in enumerate(sequence(order.get("phases"), f"{order_path}: phases")):
        where = f"{order_path}: phases[{phase_index}]"
        phase = mapping(raw, where)
        phase_id = nonempty(phase.get("id"), f"{where}.id")
        phase_order = phase.get("order")
        if type(phase_order) is not int or phase_order < 0 or phase_order in phase_orders:
            raise MatrixError(f"{where}.order: expected a unique nonnegative integer")
        if phase_id in phases:
            raise MatrixError(f"{where}.id: duplicate phase {phase_id!r}")
        phase_orders.add(phase_order)
        waves = {}
        for wave_index, raw_wave in enumerate(sequence(phase.get("waves"), f"{where}.waves")):
            wave_where = f"{where}.waves[{wave_index}]"
            wave = mapping(raw_wave, wave_where)
            wave_id = nonempty(wave.get("id"), f"{wave_where}.id")
            if wave_id in wave_ids or type(wave.get("parallel")) is not bool:
                raise MatrixError(f"{wave_where}: duplicate wave or missing boolean parallel flag")
            wave_ids.add(wave_id)
            waves[wave_id] = wave_index
            wave_stacks = string_list(
                wave.get("stacks"), f"{wave_where}.stacks", allow_empty=False
            )
            for stack_index, stack_id in enumerate(wave_stacks):
                if stack_id in wave_positions:
                    raise MatrixError(f"{wave_where}: duplicate stack assignment {stack_id!r}")
                wave_positions[stack_id] = (phase_order, wave_index, stack_index)
        phases[phase_id] = (phase_order, waves)

    stacks: dict[str, dict] = {}
    paths: set[str] = set()
    for index, raw in enumerate(sequence(order.get("stacks"), f"{order_path}: stacks")):
        where = f"{order_path}: stacks[{index}]"
        stack = mapping(raw, where)
        stack_id = nonempty(stack.get("id"), f"{where}.id")
        path = stack_path(stack.get("path"), f"{where}.path")
        phase = nonempty(stack.get("phase"), f"{where}.phase")
        wave = nonempty(stack.get("wave"), f"{where}.wave")
        if stack_id in stacks or path in paths:
            raise MatrixError(f"{where}: duplicate stack ID or path: {stack_id!r}, {path!r}")
        if phase not in phases or wave not in phases[phase][1]:
            raise MatrixError(f"{where}: unknown phase/wave {phase!r}/{wave!r}")
        if stack_id not in wave_positions or wave_positions[stack_id][:2] != (
            phases[phase][0], phases[phase][1][wave]
        ):
            raise MatrixError(
                f"{where}: stack {stack_id!r} does not match its phase/wave assignment"
            )
        deps = string_list(stack.get("depends_on"), f"{where}.depends_on")
        stacks[stack_id] = {
            "stack_id": stack_id, "path": path, "phase": phase, "wave": wave,
            "depends_on": deps, "owners": owners.get(path),
        }
        paths.add(path)

    missing_assignments = set(stacks) ^ set(wave_positions)
    if missing_assignments:
        raise MatrixError(
            f"{order_path}: stack/wave assignments disagree: {sorted(missing_assignments)}"
        )
    discovered = discover_stacks(root)
    if paths != discovered or paths != set(owners):
        raise MatrixError(
            f"inventory and live stacks disagree: unlisted live={sorted(discovered - paths)}, "
            f"missing live={sorted(paths - discovered)}, "
            f"missing owners={sorted(paths - owners.keys())}, "
            f"extra owners={sorted(owners.keys() - paths)}"
        )
    for stack_id, entry in stacks.items():
        for dependency in entry["depends_on"]:
            if (dependency not in stacks or
                    wave_positions[dependency][:2] >= wave_positions[stack_id][:2]):
                raise MatrixError(
                    f"{order_path}: {stack_id!r} depends on unknown, "
                    f"same-wave, or later stack {dependency!r}"
                )
    return [stacks[stack_id] for stack_id in sorted(stacks, key=wave_positions.__getitem__)]


def no_duplicate_json(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise MatrixError(f"changed-stacks JSON: duplicate key {key!r}")
        result[key] = value
    return result


def read_changed(source: str) -> set[str]:
    try:
        if source == "-":
            data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        else:
            with Path(source).open("rb") as stream:
                data = stream.read(MAX_INPUT_BYTES + 1)
    except (OSError, ValueError) as exc:
        raise MatrixError(f"changed-stacks source {source!r}: cannot read: {exc}") from exc
    if len(data) > MAX_INPUT_BYTES:
        raise MatrixError(f"changed-stacks source {source!r}: exceeds 1 MiB limit")
    try:
        document = json.loads(data.decode("utf-8"), object_pairs_hook=no_duplicate_json)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise MatrixError(f"changed-stacks source {source!r}: invalid UTF-8 JSON: {exc}") from exc
    if not isinstance(document, dict) or set(document) != {"stacks"}:
        raise MatrixError("changed-stacks JSON: expected exactly one 'stacks' key")
    paths = [stack_path(value, f"changed-stacks.stacks[{index}]") for index, value in enumerate(
        sequence(document["stacks"], "changed-stacks.stacks")
    )]
    if len(paths) != len(set(paths)):
        raise MatrixError("changed-stacks.stacks: duplicate stack path")
    return set(paths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--changed-stacks", required=True, metavar="FILE",
                        help="detector JSON file, or - for UTF-8 stdin "
                             "(relative file paths use the current directory)")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2],
                        help="repository root (default: root containing this script)")
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve(strict=True)
        if not (root / "go.mod").is_file():
            raise MatrixError(f"{root}: not a repository root (go.mod missing)")
        changed = read_changed(args.changed_stacks)
        entries = inventory_entries(root)
        known = {entry["path"] for entry in entries}
        if unknown := changed - known:
            raise MatrixError(f"changed-stacks JSON: unknown stack paths: {sorted(unknown)}")
        result = {"matrix": {"include": [entry for entry in entries if entry["path"] in changed]}}
        print(json.dumps(result, separators=(",", ":")))
        return 0
    except (MatrixError, OSError, ValueError) as exc:
        print(f"build-plan-matrix: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
