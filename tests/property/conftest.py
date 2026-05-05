"""Hypothesis profile registration for the property-test suite.

Local default: 50 examples per property (fast feedback).
CI: 200 examples per property (set HYPOTHESIS_PROFILE=ci).
"""

from __future__ import annotations

import os

from hypothesis import HealthCheck, settings

settings.register_profile("default", max_examples=50, deadline=2000)
settings.register_profile(
    "ci",
    max_examples=200,
    deadline=5000,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))
