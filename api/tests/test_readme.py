from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text()


def test_readme_leads_with_compose_and_ports() -> None:
    assert "docker compose up --build" in README
    assert "localhost:3000" in README
    assert "8000" in README
    assert "10 seconds" in README or "10s" in README
    assert "50" in README
    assert "2 seconds" in README or "2s" in README
    assert "30-second" in README or "30s" in README


def test_readme_has_mermaid_architecture() -> None:
    assert "```mermaid" in README
    for token in ("redpanda", "postgres", "producer", "consumer", "api", "dashboard"):
        assert token in README.lower()
    assert "/internal/" in README or "internal/scored" in README


def test_readme_metrics_are_not_accuracy() -> None:
    assert "PR-AUC" in README
    assert "not accuracy" in README.lower()
    assert "0.17%" in README
    assert "ml/artifacts/pr_curve.png" in README
    assert (ROOT / "ml/artifacts/pr_curve.png").is_file()
    assert (ROOT / "ml/artifacts/pr_curve.png").stat().st_size > 1000


def test_readme_has_future_work() -> None:
    assert "## Future Work" in README
    lowered = README.lower()
    for token in ("shap", "autoencoder", "hosted", "smote"):
        assert token in lowered


def test_readme_embeds_demo_gif() -> None:
    assert "assets/demo.gif" in README


def test_demo_gif_exists_and_is_bounded() -> None:
    path = ROOT / "assets/demo.gif"
    assert path.is_file()
    data = path.read_bytes()
    assert data[:4] == b"GIF8"
    size = path.stat().st_size
    assert 10_000 < size <= 8_000_000
