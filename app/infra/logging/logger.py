import logging
import logging.config
import pathlib
from typing import Any

import yaml

_LOGGER = None


def _get_config() -> dict:
    config_path = (pathlib.Path(__file__).parent / "config.yaml").resolve().as_posix()

    with open(config_path, "r") as config_file:
        return yaml.safe_load(config_file)


def create_logger(with_process_name: bool = False) -> logging.Logger:
    config = _get_config()

    if with_process_name:
        config["formatters"]["default"]["format"] = config["formatters"]["default-with-process"]["format"]

    logging.config.dictConfig(config)
    return logging.getLogger("uvicorn")


def get_logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is None:
        _LOGGER = create_logger()
    return _LOGGER


class LazyLogger:
    def __getattr__(self, name: str) -> Any:
        return getattr(get_logger(), name)


logger: logging.Logger = LazyLogger()  # type: ignore
