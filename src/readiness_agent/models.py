"""Validated input and output contracts. Ground truth is never part of a bundle."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json

CAUSES = {"probe_port_mismatch", "probe_path_mismatch", "dependency_unavailable",
          "healthy", "insufficient_evidence"}
KINDS = {"pod_status", "probe_config", "probe_result", "app_log", "limitation"}


def exact_keys(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("Unexpected or missing contract fields")


@dataclass(frozen=True)
class Observation:
    id: str
    kind: str
    source: str
    text: str

    @classmethod
    def parse(cls, value):
        exact_keys(value, ("id", "kind", "source", "text"))
        if not all(isinstance(v, str) and v.strip() for v in value.values()):
            raise ValueError("Observation fields must be nonempty strings")
        if value["kind"] not in KINDS or len(value["text"]) > 24000:
            raise ValueError("Unsupported observation kind or size")
        return cls(**value)


@dataclass(frozen=True)
class Bundle:
    schema: int
    target: str
    observations: tuple[Observation, ...]

    @classmethod
    def parse(cls, value):
        exact_keys(value, ("schema", "target", "observations"))
        if type(value["schema"]) is not int or value["schema"] != 1:
            raise ValueError("Unsupported bundle schema")
        if not isinstance(value["target"], str) or not 1 <= len(value["target"]) <= 300:
            raise ValueError("Invalid target")
        if not isinstance(value["observations"], list) or len(value["observations"]) > 100:
            raise ValueError("Invalid observation list")
        obs = tuple(Observation.parse(x) for x in value["observations"])
        if sum(len(o.text.encode()) for o in obs) > 128000:
            raise ValueError("Evidence bundle exceeds the text budget")
        if len({x.id for x in obs}) != len(obs):
            raise ValueError("Duplicate evidence IDs")
        return cls(1, value["target"], obs)

    def to_dict(self):
        return {"schema": 1, "target": self.target,
                "observations": [asdict(x) for x in self.observations]}


@dataclass(frozen=True)
class Diagnosis:
    cause: str
    summary: str
    evidence_ids: tuple[str, ...]
    recommendation: str
    uncertainty: str

    @classmethod
    def parse(cls, value, bundle):
        exact_keys(value, ("cause", "summary", "evidence_ids", "recommendation", "uncertainty"))
        if not isinstance(value["cause"], str) or value["cause"] not in CAUSES:
            raise ValueError("Unsupported cause")
        for key in ("summary", "recommendation", "uncertainty"):
            if not isinstance(value[key], str) or not 1 <= len(value[key]) <= 4000:
                raise ValueError("Invalid diagnosis text")
        ids = value["evidence_ids"]
        if not isinstance(ids, list) or any(not isinstance(x, str) for x in ids):
            raise ValueError("Invalid evidence references")
        if len(ids) != len(set(ids)) or not set(ids) <= {o.id for o in bundle.observations}:
            raise ValueError("Unknown or duplicate evidence references")
        if value["cause"] != "insufficient_evidence" and not ids:
            raise ValueError("A conclusion requires evidence")
        return cls(value["cause"], value["summary"], tuple(ids),
                   value["recommendation"], value["uncertainty"])

    def to_dict(self):
        value = asdict(self)
        value["evidence_ids"] = list(self.evidence_ids)
        return value


def load_bundle(path):
    with open(path, encoding="utf-8") as stream:
        return Bundle.parse(json.load(stream))
