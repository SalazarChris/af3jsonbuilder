"""The serializer: one function, one encoding policy (plan §11).

``encode(document) -> bytes`` turns the wire document produced by
``transform`` into the exact byte sequence of a generated AF3 input file:

- UTF-8, no byte-order mark, exactly one trailing newline;
- ``LF`` line endings on every host platform (binary pipeline — no
  platform translation), so a file built on Windows is byte-identical to
  one built on Linux;
- fixed indentation and separators;
- key order exactly as produced by ``transform`` — never re-sorted,
  because ordering is a transformation decision;
- no timestamps, no host information, no environment-derived values —
  which is what makes byte-level golden tests possible.

The serializer contains no conditionals on field names. If a change seems
to require one, the change belongs in ``transform`` (plan §11); an
architecture test keeps that true (``tests/architecture``).
"""

from __future__ import annotations

import json

from configbuilder.transform.engine import WireDocument

__all__ = ["EncodeError", "encode", "encode_to_file"]


class EncodeError(Exception):
    """Raised when the document cannot be serialized under the fixed
    encoding policy (structural problems — never user-fixable input)."""


def _reject_unpaired_surrogates(document) -> None:
    """UTF-8 cannot encode unpaired surrogates; ``json.dumps`` with
    ``ensure_ascii=False`` would carry them into ``str.encode`` and fail
    with an inscrutable codec error deep inside the pipeline. Diagnose the
    offending path here instead — serializer errors name the problem, they
    never mangle the output."""

    def walk(value, path):
        if isinstance(value, str):
            for index, char in enumerate(value):
                if 0xD800 <= ord(char) <= 0xDFFF:
                    raise EncodeError(
                        "unpaired surrogate at document path %r (offset %d); "
                        "text must be valid Unicode" % (path, index)
                    )
        elif isinstance(value, dict):
            for key, item in value.items():
                walk(key, path + "[key]")
                walk(item, path + "." + str(key))
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                walk(item, path + "[%d]" % index)

    walk(document, "$")


def encode(document: WireDocument) -> bytes:
    """Serialize the wire document to bytes under the fixed policy."""
    if not isinstance(document, dict):
        raise EncodeError("encode expects the WireDocument produced by transform")
    _reject_unpaired_surrogates(document)
    try:
        text = json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
            separators=(",", ": "),
            sort_keys=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        # NaN/Infinity, circular references, or a non-serializable value:
        # surfaced as the serializer's own error type, never a raw json
        # module exception leaking into the pipeline.
        raise EncodeError(
            "document is not serializable under the fixed policy: %s" % error
        ) from error
    data = text.encode("utf-8") + b"\n"
    if b"\r" in data:
        # Defense in depth: JSON escapes control characters in string
        # values, so a raw CR byte cannot normally occur. If it ever does,
        # the LF-only guarantee (plan §11) fails loudly rather than
        # silently producing platform-dependent output.
        raise EncodeError("encoded output contains a carriage return; policy is LF-only")
    return data


def encode_to_file(document: WireDocument, path) -> None:
    """Write the encoded bytes to ``path`` in binary mode.

    Binary mode is the point: text mode would translate ``\\n`` to
    ``os.linesep`` on Windows and break byte determinism (plan §11).
    There is deliberately no encoding parameter — the policy has exactly
    one encoding.
    """
    data = encode(document)
    with open(path, "wb") as handle:
        handle.write(data)
