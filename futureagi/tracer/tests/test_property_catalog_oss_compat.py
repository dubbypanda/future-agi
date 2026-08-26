"""OSS/self-host boundary checks for the unified property catalog."""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

_REPOSITORY = Path(__file__).resolve().parents[3]
_BACKEND = _REPOSITORY / "futureagi"
_CATALOG_PACKAGE = (
    _BACKEND / "tracer" / "services" / "clickhouse" / "v2" / "property_catalog"
)


def _import_targets(path: Path) -> set[str]:
    targets: set[str] = set()
    for node in ast.walk(
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    ):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            targets.add(node.module)
    return targets


def test_unified_catalog_modules_do_not_import_ee() -> None:
    modules = sorted(_CATALOG_PACKAGE.glob("*.py"))
    modules.append(
        _BACKEND
        / "tracer"
        / "management"
        / "commands"
        / "ch25_property_catalog_dev_rollout.py"
    )

    violations = {
        str(module.relative_to(_REPOSITORY)): sorted(
            target
            for target in _import_targets(module)
            if target == "ee" or target.startswith("ee.")
        )
        for module in modules
    }
    assert not {path: targets for path, targets in violations.items() if targets}


def test_root_oss_compose_keeps_unified_catalog_explicitly_off() -> None:
    compose = yaml.safe_load(
        (_REPOSITORY / "docker-compose.yml").read_text(encoding="utf-8")
    )
    services = compose["services"]

    assert {"postgres", "clickhouse", "fi-collector"} <= services.keys()
    assert "kafka" not in services
    assert "fi-property-catalog-consumer" not in services

    collector_environment = services["fi-collector"]["environment"]
    assert collector_environment["FI_CATALOG_MODE"] == "disabled"
    assert collector_environment["FI_PROPERTY_CATALOG_MODE"] == "disabled"

    backend_environment = compose["x-backend-env"]
    assert backend_environment["PROPERTY_CATALOG_READ_MODE"].endswith(":-off}")
    assert backend_environment["PROPERTY_CATALOG_DEV_RECONCILE_ENABLED"].endswith(
        ":-false}"
    )


def test_oss_collector_image_builds_both_unified_processes() -> None:
    dockerfile = (_REPOSITORY / "fi-collector" / "Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "./cmd/fi-collector" in dockerfile
    assert "./cmd/fi-property-catalog-consumer" in dockerfile
    assert (
        "COPY --from=build /out/fi-property-catalog-consumer "
        "/usr/local/bin/fi-property-catalog-consumer"
    ) in dockerfile
