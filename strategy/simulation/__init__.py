"""Original synthetic simulator boundary; no game or external-engine runtime."""

from .contracts import SimulatorAdapter
from .toy import ToySimulator

__all__ = ("SimulatorAdapter", "ToySimulator")
