"""fish/__main__.py — 兼容 ``toy_engine.tools_lib`` 的 DEFAULT_FACTORY_SPEC。

08-tools.md 把 ``fish.__main__:FISH_FACTORY`` 作为默认 factory 字符串；本文件
仅做 re-export，**不**触发任何副作用。``python -m fish.main`` 仍然走 GUI/headless 入口。
"""

from __future__ import annotations

from fish.factory import FISH_FACTORY, make_factory

__all__ = ["FISH_FACTORY", "make_factory"]
