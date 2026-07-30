import sys

import pytest

from localwhisper.single_instance import SingleInstance


@pytest.mark.skipif(sys.platform != "win32", reason="Windows named mutex")
def test_named_mutex_rejects_second_instance():
    first = SingleInstance(r"Local\LocalWhisper.Test.Singleton")
    second = SingleInstance(r"Local\LocalWhisper.Test.Singleton")
    assert first.acquire()
    try:
        assert not second.acquire()
    finally:
        first.release()
        second.release()
