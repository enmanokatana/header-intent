"""Load/dump a LibrarySpec as YAML."""
from pathlib import Path

import yaml

from .schema import LibrarySpec, to_dict, from_dict


def dump_yaml(spec: LibrarySpec, path) -> None:
    Path(path).write_text(yaml.safe_dump(to_dict(spec), sort_keys=False))

def dumps_yaml(spec: LibrarySpec) -> str:
    return yaml.safe_dump(to_dict(spec), sort_keys=False)

def load_yaml(path) -> LibrarySpec:
    return from_dict(yaml.safe_load(Path(path).read_text()))

def loads_yaml(text: str) -> LibrarySpec:
    return from_dict(yaml.safe_load(text))