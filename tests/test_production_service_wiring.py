"""Public entry points compose real research and editorial generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from ai_video_factory import workflow_cli
from ai_video_factory.profiles.models import ProfileSpec
from ai_video_factory.profiles.store import ProfileStore
from ai_video_factory.research_pipeline import Extraction
from ai_video_factory.workflow import services
from ai_video_factory.workflow.models import Chapter, Scene, ScriptBundle, Shot


def _store(tmp_path: Path) -> ProfileStore:
    store = ProfileStore(tmp_path / "profiles.sqlite3")
    store.create_profile(ProfileSpec.model_validate({
        "profile_id": "canal", "name": "Canal", "language": "pt-BR",
        "operation_budget": {"max_external_calls": 10},
    }))
    return store


def _script_generator(context: Any, research: Any) -> ScriptBundle:
    scenes: list[Scene] = []
    for index, claim in enumerate(research.claims, start=1):
        qualification = (
            "Fontes divergentes; tratar como hipótese atribuída."
            if claim.classification != "confirmed fact" or not claim.verified
            else "Afirmação sustentada pelo dossiê."
        )
        scene_id = f"scene-{index:02d}"
        scenes.append(Scene(
            scene_id=scene_id,
            title=f"Capítulo {index}",
            narration_text=f"{claim.text} {qualification}",
            estimated_seconds=8.0,
            shots=[Shot(
                shot_id=f"{scene_id}-shot",
                visual=f"Imagem para {claim.text}",
                intent=qualification,
                claim_refs=[claim.claim_id],
            )],
        ))
    return ScriptBundle(
        title=context.topic,
        logline=context.request.angle,
        language=context.language,
        chapters=[Chapter(chapter_id=f"c{i}", title=f"Capítulo {i}",
                          scene_ids=[f"scene-{i:02d}"]) for i in range(1, len(scenes) + 1)],
        scenes=scenes,
        estimated_duration_seconds=sum(scene.estimated_seconds for scene in scenes),
    )


def _invoke(tmp_path: Path, *extra: str) -> Any:
    return CliRunner().invoke(workflow_cli.workflow_app, [
        "run", "--profile", "canal", "--topic", "Tema informado",
        "--through", "script", "--production", "wire-prod",
        "--base-dir", str(tmp_path / "projects"), "--budget-calls", "10",
        *extra,
    ])


def test_default_cli_research_discovers_fetches_and_persists_evidence(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(workflow_cli, "open_store", lambda: _store(tmp_path))

    queries: list[str] = []

    def discovery(topic: str) -> list[dict[str, str]]:
        queries.append(topic)
        return [{"url": "https://b.example/b", "topic": topic}]

    def transport(url: str) -> str:
        return "Texto real longo o suficiente sobre o tema. A cresce steady in the source material."

    def extractor(topic: str, contents: list[Any], *, identity: Any = None) -> list[Extraction]:
        return [Extraction(
            claim="Fato extraído do material: A cresce steady",
            quote="A cresce steady", classification="confirmed fact",
        ) for _ in contents]

    monkeypatch.setattr(services, "default_research_transports", lambda: {
        "source_discovery": discovery,
        "transport": transport,
        "production_extractor": extractor,
    })
    monkeypatch.setattr(services, "default_script_generator", lambda: _script_generator)

    result = _invoke(tmp_path, "--seed-source-url", "https://a.example/a")

    assert result.exit_code == 0, result.output
    assert queries == ["Tema informado"]
    project = tmp_path / "projects" / "canal" / "wire-prod"
    research_path = project / "artifacts" / "01_research" / "research_bundle.json"
    research = json.loads(research_path.read_text(encoding="utf-8"))
    assert research["topic"] == "Tema informado"
    assert any(claim["evidence"] for claim in research["claims"])
    assert len(research["sources"]) >= 2
    assert any(path.is_file() for path in (project / "artifacts" / "01_research").rglob("*.txt"))
    script = json.loads(
        (project / "artifacts" / "02_script" / "script_bundle.json").read_text(encoding="utf-8")
    )
    assert any("Fato extraído" in scene["narration_text"] for scene in script["scenes"])
    assert script["language"] == "pt-BR"


def test_without_material_research_fails_explicitly(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(workflow_cli, "open_store", lambda: _store(tmp_path))
    monkeypatch.setattr(services, "default_research_transports", lambda: {
        "source_discovery": lambda topic: [],
        "transport": lambda url: "texto",
        "production_extractor": lambda topic, contents: [],
    })

    result = _invoke(tmp_path)

    assert result.exit_code == 2
    assert "no seed or discovered sources" in result.output


def test_script_qualifies_unsupported_and_contradictory_claims(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(workflow_cli, "open_store", lambda: _store(tmp_path))

    def transport(url: str) -> str:
        return "Texto longo o suficiente. A grows in one source and A shrinks in another diverging source."

    def extractor(topic: str, contents: list[Any], *, identity: Any = None) -> list[Extraction]:
        result = []
        for content in contents:
            quote = "A grows" if "a.example" in content.url else "A shrinks"
            result.append(Extraction(
                claim=f"Afirmação divergente: {quote}",
                quote=quote, classification="reported claim",
            ))
        return result

    monkeypatch.setattr(services, "default_research_transports", lambda: {
        "source_discovery": lambda topic: [],
        "transport": transport,
        "production_extractor": extractor,
    })
    monkeypatch.setattr(services, "default_script_generator", lambda: _script_generator)

    result = _invoke(
        tmp_path, "--seed-source-url", "https://a.example/a",
        "--seed-source-url", "https://b.example/b",
    )

    assert result.exit_code == 0, result.output
    project = tmp_path / "projects" / "canal" / "wire-prod"
    research = json.loads(
        (project / "artifacts" / "01_research" / "research_bundle.json").read_text(encoding="utf-8")
    )
    assert research["contradictions"]
    script = json.loads(
        (project / "artifacts" / "02_script" / "script_bundle.json").read_text(encoding="utf-8")
    )
    assert any("hipótese atribuída" in scene["narration_text"] for scene in script["scenes"])
