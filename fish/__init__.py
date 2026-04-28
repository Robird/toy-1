"""fish — MVP 业务包骨架（M3-01 起）。

子模块按需显式 import；本文件只 re-export 工厂入口（M3-10 起）。
模块布局见 fish-doc/mvp/00-overview.md §5。
"""

__version__ = "0.0.1"

# M3-10：暴露 GameFactory 入口供 ``--factory fish:make_factory`` 加载。
# 模块级 import 必须无副作用（不开窗口、不读取环境）—— ``fish.factory`` 满足。
from fish.factory import FISH_FACTORY, FishGameFactory, make_factory  # noqa: E402,F401

__all__ = ["FISH_FACTORY", "FishGameFactory", "make_factory"]
