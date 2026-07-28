"""CybORG simulator backend adapter for RAES.

Per RAES ADR-069 §3 the CybORG adapter is a *conformant simulator backend*
behind the existing RAES backend protocol surface (Provisioner, Orchestrator,
Evaluator, ParticipantRuntime). It publishes a ``backend-manifest-v2``, declares
only evidence-backed capabilities, and keeps native CybORG state, gym/PettingZoo
tuples, reward vectors, action ids, and simulator object reprs adapter-private.

REP-002 stands up this package as a buildable skeleton. The CAGE-2 mapping
ledger (``mapping/``) is authored under REP-003; the backend protocol
implementations under REP-004; replicated-run equivalence evidence under
REP-005.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.0.0"
