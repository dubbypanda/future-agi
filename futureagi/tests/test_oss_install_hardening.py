from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = ROOT / "docker-compose.yml"
INSTALL_SH = ROOT / "bin" / "install"
INSTALL_PS1 = ROOT / "bin" / "install.ps1"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _compose_config() -> dict[str, object]:
    if shutil.which("docker") is None:
        pytest.skip("docker CLI is unavailable")
    environment = os.environ.copy()
    environment.update(
        {
            "FI_COLLECTOR_VERSION": "local",
            "PROPERTY_CATALOG_KAFKA_CPUS": "1.0",
            "PROPERTY_CATALOG_KAFKA_MEMORY": "1G",
            "PROPERTY_CATALOG_KAFKA_HEAP_OPTS": "-Xms256m -Xmx512m",
            "FI_COLLECTOR_CPUS": "1.0",
            "FI_COLLECTOR_MEMORY": "1G",
            "PROPERTY_CATALOG_CONSUMER_CPUS": "0.5",
            "PROPERTY_CATALOG_CONSUMER_MEMORY": "512M",
            "PROPERTY_CATALOG_SUPERVISOR_CPUS": "0.5",
            "PROPERTY_CATALOG_SUPERVISOR_MEMORY": "768M",
        }
    )
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"docker compose config failed: {result.stderr}")
    return json.loads(result.stdout)


def test_compose_builds_the_shared_collector_image_with_bounded_resources() -> None:
    config = _compose_config()
    services = config["services"]
    assert isinstance(services, dict)

    collector = services["fi-collector"]
    consumer = services["fi-property-catalog-consumer"]
    assert collector["image"] == "futureagi/fi-collector:local"
    assert consumer["image"] == "futureagi/fi-collector:local"
    assert Path(collector["build"]["context"]).name == "fi-collector"
    assert Path(consumer["build"]["context"]).name == "fi-collector"
    assert consumer["entrypoint"] == ["/usr/local/bin/fi-property-catalog-consumer"]

    kafka = services["property-catalog-kafka"]
    assert kafka["environment"]["KAFKA_HEAP_OPTS"] == "-Xms256m -Xmx512m"
    supervisor = services["property-catalog-supervisor"]
    assert "--once" in " ".join(supervisor["command"])
    assert supervisor["healthcheck"]["test"] == [
        "CMD-SHELL",
        "test -f /tmp/property-catalog-supervisor.ready",
    ]
    for service_name in (
        "property-catalog-kafka",
        "fi-collector",
        "fi-property-catalog-consumer",
        "property-catalog-supervisor",
    ):
        assert services[service_name]["cpus"] > 0
        assert int(services[service_name]["mem_limit"]) > 0
        limits = services[service_name]["deploy"]["resources"]["limits"]
        assert limits["cpus"] > 0
        assert int(limits["memory"]) > 0


def test_installers_gate_success_on_the_full_catalog_path() -> None:
    shell = _read(INSTALL_SH)
    powershell = _read(INSTALL_PS1)
    required_services = (
        "property-catalog-kafka",
        "property-catalog-topic-init",
        "property-catalog-clickhouse-bootstrap",
        "property-catalog-postgres-bootstrap",
        "fi-collector",
        "fi-property-catalog-consumer",
        "property-catalog-supervisor",
        "backend",
    )
    for service in required_services:
        assert service in shell
        assert service in powershell

    assert "INSTALL_READY_TIMEOUT_SECONDS" in shell
    assert "INSTALL_STABILITY_SECONDS" in shell
    assert "Stack did not become fully ready" in shell
    assert "Stack did not become fully ready" in powershell
    assert "Backend did not pass /health/" not in shell
    assert "Backend did not pass /health/" not in powershell


def test_installers_cover_kafka_port_and_all_catalog_persistent_state() -> None:
    shell = _read(INSTALL_SH)
    powershell = _read(INSTALL_PS1)
    for installer in (shell, powershell):
        assert "PROPERTY_CATALOG_KAFKA_PORT" in installer
        assert "property-catalog-kafka-data" in installer
        assert "fi-collector-data" in installer
        assert "--ignore-buildable" in installer

    assert "--wipe-volumes" in shell
    assert "WipeVolumes" in powershell
    assert "docker volume prune" not in shell
    assert "docker system prune" not in shell
    assert "docker volume prune" not in powershell
    assert "docker system prune" not in powershell


def test_shell_installer_parses() -> None:
    result = subprocess.run(
        ["bash", "-n", str(INSTALL_SH)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_power_shell_installer_parses_when_pwsh_is_available() -> None:
    if shutil.which("pwsh") is None:
        pytest.skip("pwsh is unavailable")
    command = (
        "$tokens=$null; $errors=$null; "
        "[System.Management.Automation.Language.Parser]::ParseFile("
        f"'{INSTALL_PS1}', [ref]$tokens, [ref]$errors) > $null; "
        "if ($errors.Count) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }"
    )
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", command],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
