"""Shared test helpers.

`requires` behaves like `unittest.skipUnless`, except that a required
integration (FFmpeg, the built native player) fails instead of skipping when
HARMONIC_REQUIRE_INTEGRATION=1. `just release` sets it, so a release cannot
pass with its decoder and native checks silently skipped. Integrations the
README documents as optional (projectM, global todo tools, fzf) keep using
plain skipUnless.
"""

import functools
import os
import unittest

REQUIRE_ENV = "HARMONIC_REQUIRE_INTEGRATION"


def required() -> bool:
    return os.environ.get(REQUIRE_ENV) == "1"


def requires(condition: object, reason: str):
    if condition or not required():
        return unittest.skipUnless(condition, reason)
    message = f"{REQUIRE_ENV}=1 but a required integration is missing: {reason}"

    def decorate(target):
        if isinstance(target, type):
            def set_up_class(cls):
                raise AssertionError(message)
            target.setUpClass = classmethod(set_up_class)
            return target

        @functools.wraps(target)
        def fail(*args, **kwargs):
            raise AssertionError(message)
        return fail
    return decorate
