"""Offline, deterministic strategy advice. No capture or input dependencies."""

from .contracts import CandidateAction, Decision, MatchState, Observation, Outcome
from .policy import decide, filter_candidates, generate_candidates
from .state import reduce_observation

__all__ = ["CandidateAction", "Decision", "MatchState", "Observation", "Outcome",
           "decide", "filter_candidates", "generate_candidates", "reduce_observation"]
