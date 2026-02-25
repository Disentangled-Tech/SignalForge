"""Pack engine interfaces for scoring and analysis (Phase 1, Plan Step 1.1).

Abstract interfaces enable pack injection into scoring and analysis without
tight coupling to the concrete Pack dataclass. Behavior remains identical;
interfaces prepare for Phase 2 (CTO pack extraction).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.packs.loader import Pack


class PackScoringInterface(ABC):
    """Abstract interface for pack-provided scoring config.

    Implementations provide pain_signal_weights and stage_bonuses used by
    the deterministic scoring engine. Phase 2: All weights come from pack.
    """

    @abstractmethod
    def get_pain_signal_weights(self) -> dict[str, int]:
        """Return pain signal key -> weight mapping."""
        ...

    @abstractmethod
    def get_stage_bonuses(self) -> dict[str, int]:
        """Return stage name -> bonus mapping."""
        ...


class PackAnalysisInterface(ABC):
    """Abstract interface for pack-provided analysis prompt selection.

    Implementations provide prompt names for stage classification, pain
    signal detection, and explanation generation. Phase 2: Packs may
    override prompts; for now fractional_cto_v1 uses defaults.
    """

    @abstractmethod
    def get_stage_classification_prompt(self) -> str:
        """Return prompt name for stage classification."""
        ...

    @abstractmethod
    def get_pain_signals_prompt(self) -> str:
        """Return prompt name for pain signal detection."""
        ...

    @abstractmethod
    def get_explanation_prompt(self) -> str:
        """Return prompt name for explanation generation."""
        ...


def adapt_pack_for_scoring(pack: Pack) -> PackScoringInterface:
    """Adapt a Pack to PackScoringInterface.

    Extracts pain_signal_weights and stage_bonuses from pack.scoring.
    """
    return _PackScoringAdapter(pack)


def adapt_pack_for_analysis(pack: Pack) -> PackAnalysisInterface:
    """Adapt a Pack to PackAnalysisInterface.

    Returns default prompt names for fractional_cto_v1. Phase 2: Packs
    may override via manifest or taxonomy.
    """
    return _PackAnalysisAdapter(pack)


class _PackScoringAdapter(PackScoringInterface):
    """Adapter from Pack to PackScoringInterface."""

    def __init__(self, pack: Pack) -> None:
        self._pack = pack

    def get_pain_signal_weights(self) -> dict[str, int]:
        sc = self._pack.scoring if isinstance(self._pack.scoring, dict) else {}
        return dict(sc.get("pain_signal_weights") or {})

    def get_stage_bonuses(self) -> dict[str, int]:
        sc = self._pack.scoring if isinstance(self._pack.scoring, dict) else {}
        return dict(sc.get("stage_bonuses") or {})


class _PackAnalysisAdapter(PackAnalysisInterface):
    """Adapter from Pack to PackAnalysisInterface.

    Phase 1: Returns default prompt names. Phase 2: May read from pack
    manifest/taxonomy for pack-specific prompts.
    """

    def __init__(self, pack: Pack) -> None:
        self._pack = pack

    def get_stage_classification_prompt(self) -> str:
        return "stage_classification_v1"

    def get_pain_signals_prompt(self) -> str:
        return "pain_signals_v1"

    def get_explanation_prompt(self) -> str:
        return "explanation_v1"
