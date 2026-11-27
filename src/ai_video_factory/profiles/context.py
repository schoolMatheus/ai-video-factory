"""Stage-specific memory resolution with explicit precedence and pinning."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from ai_video_factory.profiles.models import (
    LearningRevision,
    MemoryContext,
    ProfileSnapshot,
    StageName,
    TypedPatch,
    canonical_digest,
)
from ai_video_factory.profiles.store import ProfileStore

# Which settings a stage may see in its fingerprint. Keys are flat and use the
# first segment as the namespace (e.g. ``editing.music`` -> ``editing``).
STAGE_SETTING_PREFIXES: dict[StageName, tuple[str, ...]] = {
    "research": ("research", "sources", "topic"),
    "script": ("script", "language", "research"),
    "narration": ("narration", "tts", "voice", "language"),
    "media": ("media", "stock", "assets", "rights"),
    "editing": ("editing", "filmcraft"),
    "review": ("review", "qc", "packaging", "rights"),
}
_SECRET_PARTS = ("secret", "token", "password", "api_key", "credential")


def _namespace(key: str) -> str:
    return key.split(".", 1)[0]


def resolve_settings(settings: Mapping[str, Any]) -> dict[str, Any]:
    """Return the one canonical, flat representation of profile settings.

    The profile convention uses dotted keys such as ``narration.voice``. Nested
    dictionaries are flattened to that same shape, but when the same resolved
    key exists in both forms the input is ambiguous: reject it instead of
    choosing silently (one reader could then apply a value another ignores).
    """
    flat: dict[str, Any] = {}
    scalar_keys = {str(key) for key, value in settings.items() if not isinstance(value, dict)}

    def walk(prefix: str, value: Mapping[str, Any]) -> None:
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(item, dict):
                walk(path, item)
                continue
            if (prefix and path in scalar_keys) or path in flat:
                raise ValueError(f"configuração ambígua: {path} usa representação plana e aninhada")
            flat[path] = item

    walk("", settings)
    return flat


def resolve_setting(settings: Mapping[str, Any], path: str, default: Any = None) -> Any:
    """Read one setting from the canonical flat representation."""
    return resolve_settings(settings).get(path, default)


def _relevant_settings(snapshot: ProfileSnapshot, stage: StageName) -> dict[str, Any]:
    prefixes = STAGE_SETTING_PREFIXES[stage]
    return {
        key: value
        for key, value in resolve_settings(snapshot.settings).items()
        if _namespace(key) in prefixes
    }


def stage_settings_digest(snapshot: ProfileSnapshot, stage: StageName) -> str:
    """Digest only the settings that can change this stage's output.

    The profile's global revision is deliberately excluded: including it would
    destroy selective invalidation (a music change must not re-run research).
    """
    return canonical_digest(
        {
            "stage": stage,
            "settings": _relevant_settings(snapshot, stage),
            "language": snapshot.language,
        }
    )


def _token_set(text: str) -> set[str]:
    return {token for token in re.findall(r"[^\W_]+", text.lower(), flags=re.UNICODE) if len(token) > 2}


def _redact(patch: TypedPatch) -> str:
    value = "<redacted>" if any(part in patch.path.lower() for part in _SECRET_PARTS) else repr(patch.value)
    return f"{patch.path} = {value}"


def _compatible(learning: LearningRevision, snapshot: ProfileSnapshot) -> bool:
    required = learning.compatible_tool_versions
    if not required:
        return True
    return all(snapshot.tool_versions.get(tool) == version for tool, version in required.items())


def _condition_applies(learning: LearningRevision, topic: str) -> bool:
    """Only rules whose application condition is met may change settings."""
    condition = (learning.condition or "always").strip()
    if condition in {"always", ""}:
        return True
    if condition.startswith("topic:"):
        token = condition.split(":", 1)[1].casefold()
        return bool(token) and token in _token_set(topic)
    return False


def build_memory_context(
    store: ProfileStore,
    snapshot: ProfileSnapshot,
    stage: StageName,
    topic: str,
    *,
    exclude_production_id: str | None = None,
) -> MemoryContext:
    """Resolve applicable rules, settings, examples and references for one stage.

    Precedence: explicit fields -> active channel learning -> inherited defaults.
    Only the current stage's observations are summarised; full history remains
    queryable through the store.
    """
    # A pinned snapshot resolves exactly the learning revisions it fixed, even
    # after those revisions were superseded in the current profile.
    learnings = [
        learning
        for learning in store.list_learnings(snapshot.profile_id, stage=stage)
        if learning.learning_id in snapshot.active_learning_ids
        and _compatible(learning, snapshot)
        and _condition_applies(learning, topic)
    ]
    # Start from explicit baseline settings when available: a learning whose
    # condition/tool version no longer applies must have no effect, not merely
    # a hidden id.
    resolved = store.base_settings(snapshot.profile_id) or resolve_settings(snapshot.settings)
    # Learnings are applied in a stable order; explicit channel choices win
    # because an explicit key is never overwritten by an inferred value.
    for learning in sorted(learnings, key=lambda item: item.learning_id):
        payload = learning.action.apply(snapshot)
        for key, value in resolve_settings(payload["settings"]).items():
            if key not in snapshot.explicit_fields:
                resolved[key] = value

    topic_tokens = _token_set(topic)
    observations = [
        item for item in store.list_observations(snapshot.profile_id, stage=stage)
        if exclude_production_id is None or item.production_id != exclude_production_id
    ]
    ordered = sorted(
        observations,
        key=lambda item: (
            -len(topic_tokens & _token_set(item.summary)),
            item.created_at,
            item.observation_id,
        ),
    )
    rules = [_redact(learning.action) for learning in learnings]
    rules.extend(f"{item.type}: {item.summary}" for item in ordered)
    examples = [
        {"type": item.type, "summary": item.summary, "evidence_refs": item.evidence_refs}
        for item in ordered
    ]
    references = sorted(
        {
            *[ref for item in ordered for ref in item.evidence_refs],
            *[ref for learning in learnings for ref in learning.evidence_ids],
        }
    )
    digest = canonical_digest(
        {
            "profile_id": snapshot.profile_id,
            "stage": stage,
            "topic": topic,
            "rules": rules,
            "settings": {
                key: value for key, value in resolved.items()
                if _namespace(key) in STAGE_SETTING_PREFIXES[stage]
            },
            "learning_ids": [item.learning_id for item in learnings],
        }
    )
    return MemoryContext(
        profile_id=snapshot.profile_id,
        stage=stage,
        topic=topic,
        digest=digest,
        rules=rules,
        settings=resolved,
        examples=examples,
        references=references,
        learning_ids=[item.learning_id for item in learnings],
        snapshot_revision=snapshot.revision,
    )
