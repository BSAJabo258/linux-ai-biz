"""BAU/BSA control plane.

BAU owns the control plane; everything else is a replaceable capability.
This package implements the trust plane (audit, permissions, approvals),
the regulation registry and policy compiler, and the domain fact
extractors (email, SMS, subscriptions, AI disclosure, privacy, IP, tax)
that feed it.
"""

__version__ = "0.2.0"
