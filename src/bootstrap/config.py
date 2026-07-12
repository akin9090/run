"""Configuration Manager(M17)を`config/default.json`から構築するヘルパー。"""

from __future__ import annotations

from pathlib import Path

from configuration_manager.domain import ConfigurationSource
from configuration_manager.manager import ConfigurationManager

_CONFIG_FILE = Path(__file__).resolve().parents[2] / "config" / "default.json"


def build_configuration_manager() -> ConfigurationManager:
    """`config/default.json`を読み込んだ`ConfigurationManager`を返す(未load状態)。

    呼び出し側が`manager.load(source)`を実行して初めて設定値を参照できる。
    """
    source = ConfigurationSource(config_file_paths=(_CONFIG_FILE,))
    return ConfigurationManager(source)
