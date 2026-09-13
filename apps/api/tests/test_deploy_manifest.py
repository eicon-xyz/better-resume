"""M6-T5: structure lint for the deployment manifests.

These checks are fast and always run, so a manifest edit cannot silently drop the worker,
the two-instance wiring or the SSE settings. They are *not* the verification of the
deployment: `scripts/compose_smoke.sh` starts the real stack and exercises the links
(recorded in docs/tickets/m6/T5-evidence.md).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE = REPO_ROOT / "compose.yaml"
NGINX = REPO_ROOT / "deploy" / "nginx.conf"
WEB_DOCKERFILE = REPO_ROOT / "apps" / "web" / "Dockerfile"
API_DOCKERFILE = REPO_ROOT / "apps" / "api" / "Dockerfile"
SMOKE = REPO_ROOT / "scripts" / "compose_smoke.sh"


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_every_service_of_the_d07_shape_exists(compose: dict[str, Any]) -> None:
    assert set(compose["services"]) >= {"postgres", "redis", "api", "worker", "nginx"}
    assert set(compose.get("volumes", {})) >= {"pgdata"}


def test_the_api_family_builds_one_image(compose: dict[str, Any]) -> None:
    images = {name: compose["services"][name]["image"] for name in ("api", "worker", "migrate")}
    assert set(images.values()) == {"better-resume-api"}


def test_api_and_worker_share_one_image(compose: dict[str, Any]) -> None:
    api, worker = compose["services"]["api"], compose["services"]["worker"]
    assert api["build"] == worker["build"]
    assert "better_resume.worker" in " ".join(worker["command"])


def test_schema_migrations_run_before_the_app_starts(compose: dict[str, Any]) -> None:
    migrate = compose["services"]["migrate"]
    assert "alembic" in " ".join(migrate["command"])
    for name in ("api", "worker"):
        assert (
            compose["services"][name]["depends_on"]["migrate"]["condition"]
            == "service_completed_successfully"
        )


def test_api_image_ships_the_migrations() -> None:
    dockerfile = API_DOCKERFILE.read_text(encoding="utf-8")

    assert "COPY migrations" in dockerfile
    assert "alembic.ini" in dockerfile


def test_api_is_scalable(compose: dict[str, Any]) -> None:
    # A fixed container_name would make `--scale api=2` fail; the port mapping to the host
    # would collide too, so only nginx publishes a port.
    assert "container_name" not in compose["services"]["api"]
    assert "ports" not in compose["services"]["api"]
    assert "container_name" not in compose["services"]["worker"]


def test_replicas_share_the_resume_volume(compose: dict[str, Any]) -> None:
    # A resume uploaded to one replica must be readable by the next request's replica.
    assert "uploads:/app/data" in compose["services"]["api"]["volumes"]
    assert "uploads" in compose["volumes"]


def test_jobs_are_enabled_where_the_worker_runs(compose: dict[str, Any]) -> None:
    for name in ("api", "worker"):
        environment = compose["services"][name]["environment"]
        assert str(environment["BR_JOBS_ENABLED"]).lower() in {"1", "true", "yes"}, name
    assert compose["services"]["worker"]["environment"]["BR_HOT_STATE_BACKEND"] == "redis"
    assert compose["services"]["api"]["environment"]["BR_LOCK_BACKEND"] == "redis"


def test_worker_health_is_a_redis_heartbeat(compose: dict[str, Any]) -> None:
    healthcheck = compose["services"]["worker"]["healthcheck"]
    command = " ".join(healthcheck["test"])
    assert "--health" in command
    assert "better_resume.worker" in command


def test_nginx_waits_for_a_healthy_api_and_owns_the_front_port(compose: dict[str, Any]) -> None:
    nginx = compose["services"]["nginx"]
    assert nginx["depends_on"]["api"]["condition"] == "service_healthy"
    # The port is ${NGINX_PORT:-8080}:80, so 8080 is the default an operator gets.
    assert any(port.endswith(":80") and "8080" in port for port in nginx["ports"])
    assert any("nginx.conf" in volume for volume in nginx["volumes"])


def test_nginx_config_proxies_api_and_streams_are_not_buffered() -> None:
    config = NGINX.read_text(encoding="utf-8")

    # The target is a variable + Docker DNS, so replicas added by --scale are seen.
    assert "set $api_upstream http://api:8000" in config
    assert "resolver 127.0.0.11" in config
    assert "proxy_buffering off" in config
    assert "proxy_set_header Upgrade $http_upgrade" in config
    assert "proxy_read_timeout 300s" in config
    assert "try_files $uri /index.html" in config
    assert "location = /healthz" in config


def test_api_image_is_non_root_and_proxy_aware() -> None:
    dockerfile = API_DOCKERFILE.read_text(encoding="utf-8")

    assert "USER app" in dockerfile
    assert "--proxy-headers" in dockerfile
    assert "uv sync --frozen" in dockerfile


def test_web_image_builds_the_spa_and_serves_it_with_nginx() -> None:
    dockerfile = WEB_DOCKERFILE.read_text(encoding="utf-8")

    assert "node:" in dockerfile
    assert "pnpm install --frozen-lockfile" in dockerfile
    assert "nginx:1.27-alpine" in dockerfile
    assert "pnpm --filter @better-resume/web build" in dockerfile


def test_smoke_script_is_the_documented_entry_point() -> None:
    script = SMOKE.read_text(encoding="utf-8")

    assert "docker compose" in script
    assert "--wait" in script
    assert "scale api=2" in script
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "scripts/compose_smoke.sh" in readme
