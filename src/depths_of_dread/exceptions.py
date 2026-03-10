"""Custom exception hierarchy for Depths of Dread."""
from __future__ import annotations


class DreadError(Exception):
    """Base exception for all game errors."""


class SaveError(DreadError):
    """Failed to save game state."""


class LoadError(DreadError):
    """Failed to load game state (corrupt, missing, tampered)."""


class RecordingError(DreadError):
    """Failed during session recording operations."""


class SpawnError(DreadError):
    """Failed to find a valid spawn position."""


class AgentError(DreadError):
    """Error in agent/bot AI operations."""


class ClaudeAPIError(AgentError):
    """Failed to communicate with Claude API."""
