"""Write JSON Schema for the contract to schema/generated/.

Per-document schemas (for validating files and frames) plus one combined `contract.schema.json`
with every type in `$defs`, which the TypeScript and Dart generators consume so shared types are
emitted once.

    uv run python -m ic_schema.export [OUT_DIR]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from ic_schema.events import AnyEvent
from ic_schema.manifest import Manifest
from ic_schema.protocol import AnyClientMessage, AnyServerMessage
from ic_schema.report import Report
from ic_schema.version import SCHEMA_VERSION

DIALECT = "https://json-schema.org/draft/2020-12/schema"
BASE_ID = "https://interview-coach.local/schema"

DOCUMENTS: dict[str, tuple[type[BaseModel], str]] = {
    "event": (AnyEvent, "Event"),
    "manifest": (Manifest, "Manifest"),
    "client_message": (AnyClientMessage, "ClientMessage"),
    "server_message": (AnyServerMessage, "ServerMessage"),
    "report": (Report, "Report"),
}

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "generated"


def _strip_titles(node: Any) -> Any:
    """Drop Pydantic's per-property titles; generators would turn each into a named alias."""
    if isinstance(node, dict):
        return {
            k: (
                _strip_titles(v)
                if k != "properties"
                else {p: _strip_titles(s) for p, s in v.items()}
            )
            for k, v in node.items()
            if k != "title"
        }
    if isinstance(node, list):
        return [_strip_titles(v) for v in node]
    return node


def _require_consts(node: Any) -> Any:
    """Mark `const` properties (the `kind` / `type` discriminators) required.

    They carry Python defaults for convenience, which would otherwise make them optional in the
    schema and break discriminated-union narrowing in TypeScript. Parsing requires them anyway.
    """
    if isinstance(node, dict):
        out = {k: _require_consts(v) for k, v in node.items()}
        props = out.get("properties")
        if isinstance(props, dict):
            consts = [p for p, s in props.items() if isinstance(s, dict) and "const" in s]
            required = list(out.get("required", []))
            out["required"] = required + [p for p in consts if p not in required]
            for p in consts:
                props[p].pop("default", None)
        return out
    if isinstance(node, list):
        return [_require_consts(v) for v in node]
    return node


def _named(defs: dict[str, Any]) -> dict[str, Any]:
    """Normalize each definition, then title it with its own name."""
    return {
        name: {**_require_consts(_strip_titles(body)), "title": name} for name, body in defs.items()
    }


def _document(model: type[BaseModel], title: str, name: str) -> dict[str, Any]:
    schema = model.model_json_schema()
    defs = _named(schema.pop("$defs", {}))
    schema = {**_require_consts(_strip_titles(schema)), "title": title}
    if defs:
        schema["$defs"] = defs
    return {
        "$schema": DIALECT,
        "$id": f"{BASE_ID}/{name}.schema.json",
        "x-schema-version": SCHEMA_VERSION,
        **schema,
    }


def _contract() -> dict[str, Any]:
    _, defs = models_json_schema(
        [(model, "validation") for model, _ in DOCUMENTS.values()],
        ref_template="#/$defs/{model}",
    )
    all_defs: dict[str, Any] = defs["$defs"]
    # Root wrappers become plain unions named after the document.
    for model, title in DOCUMENTS.values():
        if model.__name__ != title and model.__name__ in all_defs:
            all_defs[title] = all_defs.pop(model.__name__)
    text = json.dumps(all_defs)
    for model, title in DOCUMENTS.values():
        text = text.replace(f'"#/$defs/{model.__name__}"', f'"#/$defs/{title}"')
    all_defs = _named(json.loads(text))
    return {
        "$schema": DIALECT,
        "$id": f"{BASE_ID}/contract.schema.json",
        "x-schema-version": SCHEMA_VERSION,
        "title": "Contract",
        "description": "All contract types. Root properties exist only to anchor code generation.",
        "type": "object",
        "properties": {
            name: {"$ref": f"#/$defs/{title}"} for name, (_, title) in DOCUMENTS.items()
        },
        "$defs": all_defs,
    }


def render() -> dict[str, str]:
    """File name -> JSON text, deterministic."""
    out = {
        f"{name}.schema.json": _document(model, title, name)
        for name, (model, title) in DOCUMENTS.items()
    }
    out["contract.schema.json"] = _contract()
    return {k: json.dumps(v, indent=2, sort_keys=True) + "\n" for k, v in out.items()}


def main(argv: list[str]) -> None:
    out_dir = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in render().items():
        (out_dir / name).write_text(text, encoding="utf-8")
        print(f"wrote {out_dir / name}")


if __name__ == "__main__":
    main(sys.argv)
