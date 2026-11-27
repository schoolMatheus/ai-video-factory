"""Adapter from UI DTOs to the versioned domain ProfileStore."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Protocol

from ai_video_factory.ui_backend.models import (
    ConflictError,
    FeedbackRequest,
    MemoryView,
    NotFoundError,
    ProfileCreateRequest,
    ProfilePatchRequest,
    ProfileView,
    StageName,
)


def _translate(call: Any) -> Any:
    """Domain errors become typed HTTP errors at the adapter boundary."""
    from ai_video_factory.profiles.store import (
        NotFound as DomainNotFound,
        RevisionConflict,
        ScopeViolation,
    )

    try:
        return call()
    except DomainNotFound as error:
        raise NotFoundError(str(error)) from error
    except ScopeViolation as error:
        raise NotFoundError(str(error)) from error
    except RevisionConflict as error:
        raise ConflictError(str(error)) from error


class ProfileAdapter(Protocol):
    def list_profiles(self) -> list[ProfileView]: ...

    def get_profile(self, profile_id: str) -> ProfileView: ...

    def create_profile(self, payload: ProfileCreateRequest) -> ProfileView: ...

    def revise_profile(
        self, profile_id: str, payload: ProfilePatchRequest
    ) -> ProfileView: ...

    def list_memory(self, profile_id: str) -> list[MemoryView]: ...

    def add_feedback(self, profile_id: str, payload: FeedbackRequest) -> MemoryView: ...

    def suspend_learning(
        self, profile_id: str, learning_id: str, expected_revision: int, reason: str
    ) -> MemoryView: ...


class DomainProfileAdapter:
    def __init__(self, db_path: Path) -> None:
        from ai_video_factory.profiles.store import ProfileStore

        self.store = ProfileStore(db_path)

    def list_profiles(self) -> list[ProfileView]:
        return [_profile_view(snapshot) for snapshot in self.store.list_profiles()]

    def get_profile(self, profile_id: str) -> ProfileView:
        return _translate(lambda: _profile_view(self.store.get_snapshot(profile_id)))

    def create_profile(self, payload: ProfileCreateRequest) -> ProfileView:
        from ai_video_factory.profiles.models import ProfileSpec

        spec = ProfileSpec(
            profile_id=payload.profile_id,
            name=payload.name,
            language=payload.language,
            niche=payload.niche,
            explicit_fields=payload.explicit_fields,
            settings={"language": payload.language, "niche": payload.niche},
        )
        return _translate(lambda: _profile_view(self.store.create_profile(spec)))

    def revise_profile(self, profile_id: str, payload: ProfilePatchRequest) -> ProfileView:
        from ai_video_factory.profiles.models import ProfilePatch

        patch = ProfilePatch(
            name=payload.name,
            language=payload.language,
            niche=payload.niche,
            settings=payload.settings,
            explicit_fields=payload.explicit_fields or [],
        )
        return _translate(lambda: _profile_view(
            self.store.revise_profile(
                profile_id,
                patch,
                expected_revision=payload.expected_revision,
                reason=payload.reason,
            )
        ))

    def list_memory(self, profile_id: str) -> list[MemoryView]:
        snapshot = _translate(lambda: self.store.get_snapshot(profile_id))
        items: list[MemoryView] = []
        for learning in self.store.list_learnings(profile_id):
            items.append(
                MemoryView(
                    id=learning.learning_id,
                    profile_id=profile_id,
                    stage=_stage(learning.action),
                    state=learning.state,
                    summary=f"{learning.action.path} = {learning.action.value!r}",
                    origin="inferred",
                    condition=learning.condition,
                    evidence=list(learning.evidence_ids),
                    before=None,
                    after=str(learning.action.value),
                    revision=snapshot.revision,
                    updated_at=learning.activated_at,
                )
            )
        for candidate in self.store.list_candidates(profile_id):
            items.append(MemoryView(
                id=candidate.candidate_id,
                profile_id=profile_id,
                stage=candidate.stage,
                state=candidate.state,
                summary=f"hipótese: {candidate.change.path} = {candidate.change.value!r}",
                origin="inferred",
                condition=candidate.condition,
                evidence=list(candidate.evidence_ids),
                after=str(candidate.change.value),
                revision=snapshot.revision,
                updated_at=candidate.created_at,
            ))
        for observation in self.store.list_observations(profile_id):
            items.append(
                MemoryView(
                    id=observation.observation_id,
                    profile_id=profile_id,
                    stage=observation.stage,
                    state="observed",
                    summary=observation.summary,
                    origin="observed",
                    evidence=list(observation.evidence_refs),
                    revision=snapshot.revision,
                    updated_at=observation.created_at,
                )
            )
        return items

    def add_feedback(self, profile_id: str, payload: FeedbackRequest) -> MemoryView:
        from ai_video_factory.profiles.models import Observation

        identifier = hashlib.sha256(
            f"{profile_id}:{payload.summary}:{payload.production_id or ''}".encode("utf-8")
        ).hexdigest()[:24]
        self.store.record_observation(
            Observation(
                observation_id=f"obs-{identifier}",
                profile_id=profile_id,
                production_id=payload.production_id,
                stage=payload.stage,
                attempt=1,
                type="user_feedback",
                source="ui",
                summary=payload.summary,
                evidence_refs=payload.evidence,
                event_key=f"ui-feedback:{identifier}",
            )
        )
        return MemoryView(
            id=f"obs-{identifier}",
            profile_id=profile_id,
            stage=payload.stage,
            state="observed",
            summary=payload.summary,
            origin="observed",
            evidence=payload.evidence,
        )

    def suspend_learning(
        self, profile_id: str, learning_id: str, expected_revision: int, reason: str
    ) -> MemoryView:
        revised = _translate(lambda: self.store.suspend_learning(
            profile_id, learning_id, expected_revision=expected_revision, reason=reason
        ))
        return MemoryView(
            id=learning_id,
            profile_id=profile_id,
            state="suspended",
            summary=f"Suspenso: {reason}",
            origin="inferred",
            revision=revised.revision,
            updated_at=revised.created_at,
        )


def _profile_view(snapshot: Any) -> ProfileView:
    return ProfileView(
        id=snapshot.profile_id,
        name=getattr(snapshot, "name", "") or snapshot.profile_id,
        language=getattr(snapshot, "language", ""),
        niche=getattr(snapshot, "niche", ""),
        revision=snapshot.revision,
        settings=dict(getattr(snapshot, "settings", {})),
        explicit_fields=list(getattr(snapshot, "explicit_fields", [])),
    )


def _stage(action: Any) -> StageName:
    text = str(getattr(action, "stage", "") or "")
    try:
        return StageName(text)
    except ValueError:
        return StageName.research
