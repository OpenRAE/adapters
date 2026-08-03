"""Neutral gym-backend framework shared by index-published simulator adapters.

CyberBattleSim and NASim both wrap a Gymnasium environment behind one private
driver and expose the same RAES surfaces. The stateful controllers differ only
by a backend name (which seeds diagnostic codes and identifiers) and a small
per-backend configuration, so they live here once and each backend parameterizes
them. Nothing here holds a simulator semantics of its own; RAES owns every
published model.
"""

from __future__ import annotations
