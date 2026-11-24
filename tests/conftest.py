"""Fixtures for optional operating-system capabilities."""

import errno

import pytest


@pytest.fixture
def make_symlink():
    def create(link, target):
        try:
            link.symlink_to(target)
        except OSError as error:
            if error.errno in (errno.EPERM, errno.EACCES, errno.ENOSYS) or getattr(error, "winerror", None) == 1314:
                pytest.skip("creating symbolic links is unavailable for this user")
            raise
    return create
