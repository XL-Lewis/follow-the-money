from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .fetch import house, senate

DEFAULT_DATA_DIR = Path("data")


@dataclass(frozen=True)
class Config:
    data_dir: Path
    house_index_url: str = house.INDEX_URL
    senate_index_url: str = senate.INDEX_URL

    @property
    def db_path(self) -> Path:
        return self.data_dir / "ftm.sqlite"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    def ensure_dirs(self) -> None:
        self.raw_dir.mkdir(parents=True, exist_ok=True)


def default_config() -> Config:
    return Config(data_dir=DEFAULT_DATA_DIR)
