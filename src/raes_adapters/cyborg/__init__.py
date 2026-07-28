"""CybORG simulator backend adapter for RAES (optional ``cyborg`` extra).

Per RAES ADR-069 §3 the CybORG adapter is a conformant simulator backend behind
the RAES backend protocol surface (Provisioner, Orchestrator, Evaluator,
ParticipantRuntime). It keeps native CybORG state, gym/PettingZoo tuples, reward
vectors, action ids, and simulator object reprs adapter-private.

Install the simulator dependencies with ``pip install raes-adapters[cyborg]``.
The backend protocol implementations land under REP-004; the CAGE-2 mapping
ledger (:mod:`raes_adapters.cyborg.mapping`) under REP-003.
"""

from __future__ import annotations

__all__: list[str] = []
