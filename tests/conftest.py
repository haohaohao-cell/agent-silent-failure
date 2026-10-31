from __future__ import annotations

import pytest

from src.tools import ToolBox
from src.world import World


@pytest.fixture()
def world() -> World:
    return World()


@pytest.fixture()
def make_tools(world):
    from src.injector import Injector
    from src.trace import Recorder

    def _make(faults=None):
        recorder = Recorder()
        toolbox = ToolBox(world, Injector(faults or []), recorder)
        return toolbox, recorder

    return _make
