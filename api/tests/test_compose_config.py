from pathlib import Path


def test_compose_exposes_api_and_dashboard() -> None:
    text = Path("docker-compose.yml").read_text()
    assert "8000:8000" in text
    assert "3000:80" in text
    assert "api:" in text
    assert "dashboard:" in text
