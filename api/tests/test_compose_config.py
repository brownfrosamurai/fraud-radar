from pathlib import Path


def test_compose_six_services_and_internal_producer() -> None:
    text = Path("docker-compose.yml").read_text()
    for name in ("redpanda:", "postgres:", "producer:", "consumer:", "api:", "dashboard:"):
        assert name in text
    assert "8000:8000" in text
    assert "3000:80" in text
    assert "8001:8001" not in text
    assert text.count("restart: unless-stopped") == 3
    assert text.count("INTERNAL_API_SECRET: fraud-radar-streaming") == 2


def test_nginx_blocks_internal_and_upgrades_websocket() -> None:
    text = Path("dashboard/nginx.conf").read_text()
    assert "location /api/internal/" in text
    assert "Upgrade" in text
