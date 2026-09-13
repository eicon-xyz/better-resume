"""M6-T5: every response names the instance that served it.

nginx load-balances two api containers, so an operator (and the drill in T8) needs to see
*which* container answered. The header is also what the dual-instance smoke test asserts on.
"""

from __future__ import annotations

import socket

from fastapi.testclient import TestClient

from better_resume.main import create_app
from better_resume.settings import Settings

HEADER = "x-instance-id"


def test_header_defaults_to_the_hostname(client: TestClient, settings: Settings) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.headers[HEADER] == settings.instance_id
    assert response.headers[HEADER]  # never blank: the drill greps for it


def test_instance_id_comes_from_the_settings(database_url: str) -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        log_level="WARNING",
        database_url=database_url,
        instance_id="api-blue",
    )

    with TestClient(create_app(settings)) as client:
        assert client.get("/healthz").headers[HEADER] == "api-blue"


def test_default_instance_id_is_this_host() -> None:
    assert Settings(_env_file=None).instance_id == socket.gethostname()
