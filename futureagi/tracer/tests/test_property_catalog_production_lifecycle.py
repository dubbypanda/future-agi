from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tracer.management.commands import (
    ch25_property_catalog_lifecycle_controller as subject,
)
from tracer.services.clickhouse.v2.property_catalog.dev_rollout import (
    DEV_ROLLOUT_ACK,
    DevRolloutError,
    DevRolloutRequest,
)
from tracer.services.clickhouse.v2.property_catalog.dev_runtime import (
    PropertyCatalogProductionRuntimeFactory,
)
from tracer.services.clickhouse.v2.property_catalog.production_rollout import (
    PRODUCTION_LIFECYCLE_ACK,
    ProductionRolloutRequest,
)
from tracer.services.clickhouse.v2.property_catalog.reconciler import ReconcileMode
from tracer.services.clickhouse.v2.property_catalog.revision_fence_registry import (
    AtomicMultiTenantFenceFile,
)

ORG = "11111111-1111-4111-8111-111111111111"
WORKSPACE = "22222222-2222-4222-8222-222222222222"
PROJECT = "33333333-3333-4333-8333-333333333333"


def _production_request(**overrides: Any) -> ProductionRolloutRequest:
    values = {
        "organization_id": ORG,
        "workspace_id": WORKSPACE,
        "environment": "production",
        "cloud_deployment": "US",
        "dev_identity": "prod:property-catalog-lifecycle",
        "source_database": "spans",
        "target_database": "property_catalog",
        "acknowledgement": PRODUCTION_LIFECYCLE_ACK,
        "execute": True,
    }
    values.update(overrides)
    return ProductionRolloutRequest(**values)


def _settings(tmp_path: Path, **overrides: Any) -> SimpleNamespace:
    values = {
        "ENV_TYPE": "production",
        "CLOUD_DEPLOYMENT": "US",
        "PROPERTY_CATALOG_LIFECYCLE_ENABLED": True,
        "PROPERTY_CATALOG_LIFECYCLE_BOOTSTRAP_ENABLED": False,
        "PROPERTY_CATALOG_LIFECYCLE_REPAIR_EXPIRED_INCOMPLETE": False,
        "PROPERTY_CATALOG_LIFECYCLE_ACK": PRODUCTION_LIFECYCLE_ACK,
        "PROPERTY_CATALOG_LIFECYCLE_IDENTITY": ("prod:property-catalog-lifecycle"),
        "PROPERTY_CATALOG_LIFECYCLE_SOURCE_DATABASE": "spans",
        "PROPERTY_CATALOG_LIFECYCLE_TARGET_DATABASE": "property_catalog",
        "PROPERTY_CATALOG_LIFECYCLE_WORKSPACE_ALLOWLIST": (WORKSPACE,),
        "PROPERTY_CATALOG_LIFECYCLE_RUNTIME_DIRECTORY": str(tmp_path),
        "PROPERTY_CATALOG_LIFECYCLE_HEALTH_FILE": str(tmp_path / "health.json"),
        "PROPERTY_CATALOG_LIFECYCLE_POLL_SECONDS": 60,
        "PROPERTY_CATALOG_LIFECYCLE_FAILURE_BACKOFF_SECONDS": 30,
        "PROPERTY_CATALOG_LIFECYCLE_SCHEDULED_RECONCILE_WALL_MS": 1_200_000,
        "PROPERTY_CATALOG_LIFECYCLE_SPAN_WINDOW_DAYS": 366,
        "PROPERTY_CATALOG_LIFECYCLE_MAX_WALL_MS": 100_000,
        "PROPERTY_CATALOG_LIFECYCLE_WRITE_CH_HOST": "catalog.internal",
        "PROPERTY_CATALOG_LIFECYCLE_WRITE_CH_PORT": 9000,
        "PROPERTY_CATALOG_LIFECYCLE_WRITE_CH_USER": "catalog_writer",
        "PROPERTY_CATALOG_LIFECYCLE_WRITE_CH_PASSWORD": "secret",
        "PROPERTY_CATALOG_LIFECYCLE_CATALOG_EPOCH": 1,
        "PROPERTY_CATALOG_LIFECYCLE_PROJECTION_VERSION": 1,
        "PROPERTY_CATALOG_LIFECYCLE_PRODUCER_STREAM_ID": (
            "44444444-4444-4444-8444-444444444444"
        ),
        "PROPERTY_CATALOG_LIFECYCLE_REVISION_FENCE_FILE": str(
            tmp_path / "revision-fence.json"
        ),
        "PROPERTY_CATALOG_LIFECYCLE_DRAIN_PROOF_FILE": str(
            tmp_path / "producer-drain-proof-v2.json"
        ),
        "PROPERTY_CATALOG_LIFECYCLE_PRODUCER_RETIREMENT_FILE": str(
            tmp_path / "producer-state-retirements-v1.json"
        ),
        "PROPERTY_CATALOG_LIFECYCLE_EXPECTED_WRITE_CH_HOSTNAME": "catalog-0",
        "PROPERTY_CATALOG_LIFECYCLE_EXPECTED_SOURCE_CH_HOSTNAME": "spans-0",
        "PROPERTY_CATALOG_LIFECYCLE_EXPECTED_PG_DATABASE": "futureagi",
        "PROPERTY_CATALOG_LIFECYCLE_EXPECTED_PG_USER": "catalog_source_reader",
        "PROPERTY_CATALOG_LIFECYCLE_EXPECTED_PG_SERVER_ADDRESS": "10.0.0.1",
        "PROPERTY_CATALOG_LIFECYCLE_EXPECTED_PG_SERVER_PORT": 5432,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _scope() -> subject.WorkspaceScope:
    return subject.WorkspaceScope(
        organization_id=ORG,
        workspace_id=WORKSPACE,
        is_default=False,
        project_ids=(PROJECT,),
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("environment", "development", "environment='production'"),
        ("cloud_deployment", "DEV", "supported cloud"),
        ("dev_identity", "dev:controller", "production control-plane identity"),
        ("target_database", "property_catalog_dev_unit", "exactly 'property_catalog'"),
        ("acknowledgement", DEV_ROLLOUT_ACK, "exact production lifecycle"),
    ),
)
def test_production_request_rejects_cross_wired_scope(
    field: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(DevRolloutError, match=message):
        _production_request(**{field: value})


def test_dev_request_still_rejects_production_database() -> None:
    with pytest.raises(DevRolloutError, match="isolated DEV"):
        DevRolloutRequest(
            organization_id=ORG,
            workspace_id=WORKSPACE,
            environment="development",
            cloud_deployment="DEV",
            dev_identity="dev:unit-controller",
            source_database="spans",
            target_database="property_catalog",
            acknowledgement=DEV_ROLLOUT_ACK,
            execute=True,
        )


def test_production_factory_defaults_to_multi_tenant_fence_registry() -> None:
    factory = PropertyCatalogProductionRuntimeFactory(settings_object=SimpleNamespace())
    assert factory._fence_sink_factory is AtomicMultiTenantFenceFile  # noqa: SLF001


def test_controller_config_is_production_exact_and_bootstrap_off(
    tmp_path: Path,
) -> None:
    config = subject.controller_config(settings_object=_settings(tmp_path))
    assert config.target_database == "property_catalog"
    assert config.workspace_ids == (WORKSPACE,)
    assert config.bootstrap_enabled is False


@pytest.mark.parametrize(
    ("overrides", "message"),
    (
        ({"ENV_TYPE": "development"}, "ENV_TYPE=production"),
        ({"PROPERTY_CATALOG_LIFECYCLE_ENABLED": False}, "must be true"),
        ({"PROPERTY_CATALOG_LIFECYCLE_ACK": "wrong"}, "acknowledgement"),
        ({"PROPERTY_CATALOG_LIFECYCLE_TARGET_DATABASE": "default"}, "exactly"),
        ({"PROPERTY_CATALOG_LIFECYCLE_WORKSPACE_ALLOWLIST": ()}, "1..256"),
    ),
)
def test_controller_config_fails_closed(
    tmp_path: Path,
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(subject.ProductionLifecycleControllerError, match=message):
        subject.controller_config(settings_object=_settings(tmp_path, **overrides))


def test_workspace_overlay_binds_prod_settings_to_shared_runtime(
    tmp_path: Path,
) -> None:
    settings_object = _settings(tmp_path)
    config = subject.controller_config(settings_object=settings_object)
    overlay = subject.workspace_settings_overlay(
        settings_object=settings_object,
        config=config,
        scope=_scope(),
        now=datetime(2026, 8, 26, 12, 34, tzinfo=UTC),
    )

    assert overlay.PROPERTY_CATALOG_DEV_WRITE_CH_DATABASE == "property_catalog"
    assert overlay.PROPERTY_CATALOG_DEV_PROJECT_ALLOWLIST == (PROJECT,)
    assert overlay.PROPERTY_CATALOG_DEV_SPAN_UNTIL == "2026-08-26T12:00:00Z"
    assert overlay.PROPERTY_CATALOG_DEV_SPAN_SINCE == "2025-08-25T12:00:00Z"


def test_execute_request_requires_explicit_expired_revision_repair_gate(
    tmp_path: Path,
) -> None:
    settings_object = _settings(
        tmp_path,
        PROPERTY_CATALOG_LIFECYCLE_REPAIR_EXPIRED_INCOMPLETE=True,
    )
    config = subject.controller_config(settings_object=settings_object)
    overlay = subject.workspace_settings_overlay(
        settings_object=settings_object,
        config=config,
        scope=_scope(),
        now=datetime(2026, 8, 26, 12, tzinfo=UTC),
    )

    execute = subject.rollout_request(
        scope=_scope(),
        proxy=overlay,
        config=config,
    )
    status = subject.rollout_request(
        scope=_scope(),
        proxy=overlay,
        config=config,
        status=True,
    )

    assert execute.repair_expired_incomplete is True
    assert status.repair_expired_incomplete is False


def test_active_workspace_runs_incremental_reconcile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_object = _settings(tmp_path)
    config = subject.controller_config(settings_object=settings_object)
    runtimes: list[object] = []

    @contextmanager
    def fake_runtime(**_kwargs: Any):
        runtime = object()
        runtimes.append(runtime)
        yield runtime

    status_result = SimpleNamespace(
        evidence=(SimpleNamespace(evidence={"schema_ready": True, "active": True}),)
    )
    monkeypatch.setattr(subject, "managed_runtime", fake_runtime)
    monkeypatch.setattr(
        subject,
        "run_configured_production_rollout",
        lambda **_kwargs: status_result,
    )
    observed: dict[str, object] = {}

    def reconcile(**kwargs: Any) -> dict[str, object]:
        observed.update(kwargs)
        return {"reconciled": True}

    monkeypatch.setattr(subject, "run_workspace_reconcile", reconcile)
    result = subject.run_workspace(
        scope=_scope(),
        settings_object=settings_object,
        config=config,
        now=datetime(2026, 8, 26, 12, tzinfo=UTC),
        status_only=False,
    )

    assert result == {"reconciled": True}
    assert observed["mode"] is ReconcileMode.INCREMENTAL
    assert len(runtimes) == 2


def test_inactive_workspace_requires_separate_bootstrap_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_object = _settings(tmp_path)
    config = subject.controller_config(settings_object=settings_object)

    @contextmanager
    def fake_runtime(**_kwargs: Any):
        yield object()

    monkeypatch.setattr(subject, "managed_runtime", fake_runtime)
    monkeypatch.setattr(
        subject,
        "run_configured_production_rollout",
        lambda **_kwargs: SimpleNamespace(
            evidence=(
                SimpleNamespace(evidence={"schema_ready": True, "active": False}),
            )
        ),
    )

    with pytest.raises(
        subject.ProductionLifecycleControllerError,
        match="bootstrap is disabled",
    ):
        subject.run_workspace(
            scope=_scope(),
            settings_object=settings_object,
            config=config,
            now=datetime(2026, 8, 26, 12, tzinfo=UTC),
            status_only=False,
        )


def test_health_file_is_private_canonical_and_atomically_replaceable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "health.json"
    observed_at = datetime(2026, 8, 26, 12, tzinfo=UTC)
    subject._write_health(  # noqa: SLF001
        str(path),
        healthy=True,
        observed_at=observed_at,
        detail={"processed": [WORKSPACE]},
    )
    first = path.read_bytes()
    subject._write_health(  # noqa: SLF001
        str(path),
        healthy=False,
        observed_at=observed_at,
        detail={"cycle_error": "injected"},
    )

    assert first.endswith(b"\n")
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.read_bytes().endswith(b"\n")
    assert not tuple(tmp_path.glob(".property-catalog-lifecycle-health-*"))


def test_health_file_retries_partial_kernel_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "health.json"
    original_write = subject.os.write
    calls = 0

    def partial_write(descriptor: int, value: object) -> int:
        nonlocal calls
        calls += 1
        payload = bytes(value)
        return original_write(descriptor, payload[: max(1, len(payload) // 2)])

    monkeypatch.setattr(subject.os, "write", partial_write)
    subject._write_health(  # noqa: SLF001
        str(path),
        healthy=True,
        observed_at=datetime(2026, 8, 26, 12, tzinfo=UTC),
        detail={"processed": [WORKSPACE]},
    )

    assert calls > 1
    assert path.read_bytes().endswith(b"\n")


def test_workspace_scope_maps_only_default_legacy_projects() -> None:
    scope = _scope()
    with pytest.raises(subject.ProductionLifecycleControllerError, match="default"):
        replace(scope, legacy_project_ids=(PROJECT,))
