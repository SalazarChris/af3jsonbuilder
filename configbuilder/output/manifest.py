"""The generation manifest (IMPLEMENTATION_PLAN.md §13.6, MAP-015).

Project-side report of one generation run — never consumed by the external
system. **The file that is written contains only deterministic data**: it is
a function of the project and the plan, so two runs over the same inputs
produce byte-identical ``manifest.json`` files (plan §13.7, tested in §18.6).

The fields actually written are ``schema_version``, ``builder_version``,
``project_name``, ``base_fingerprint``, ``format_version``,
``contract_pin_record``, ``path_policy``, ``overwrite_policy``, ``seed_set``,
``variants`` and ``validation_summary``.

``run_info`` (timestamp, host, user, platform, pid) is built by this module for
callers that want it — diagnostics, tests of the separation itself — and is
**not** written into the manifest: a per-run timestamp in the file would make
identical regenerations differ, which is exactly what the reproducible-output
rule forbids. :func:`run_info` remains the one home of time-varying data if a
future format ever needs it.
"""

from __future__ import annotations


__all__ = ["MANIFEST_SCHEMA_VERSION", "ManifestData", "build_manifest", "run_info"]

MANIFEST_SCHEMA_VERSION = 1

# Builder version: package metadata if installed, else the fixed
# development marker. Deterministic per checkout; never per-run.
try:  # pragma: no cover - trivial import fallback
    from importlib.metadata import version as _metadata_version

    _BUILDER_VERSION = _metadata_version("configbuilder")
except Exception:  # pragma: no cover - running from an uninstalled checkout
    _BUILDER_VERSION = "0.0.0.dev0"


class ManifestData:
    """The manifest's content, separated for determinism assertions:
    ``data`` is byte-reproducible **and is what gets written**; ``run_info``
    is not reproducible, so it is carried alongside and never serialized."""

    __slots__ = ("data", "run_info")

    def __init__(self, data, run_info) -> None:
        self.data = data
        self.run_info = run_info

    def __repr__(self) -> str:
        return "ManifestData(%d variants)" % len(self.data.get("variants", ()))


def _pin_record_id(version: int, evidence=None) -> str:
    """The provenance reference for ``version`` — supplied by the operator.

    The evidence citation (e.g. a ``PIN-nnn`` record) travels in the
    model's ``Pinned.evidence``; this function passes it through verbatim
    and never reads any document. When no evidence was supplied the
    manifest records ``None`` — validation's findings explain why.
    """
    if isinstance(evidence, str) and evidence.strip():
        return evidence.strip()
    return None


def _validation_summary(report) -> dict:
    """A compact, order-stable summary of a validation report."""
    if report is None:
        return {}
    summary = {}
    counts = {}
    for finding in report.findings:
        counts[finding.severity.name] = counts.get(finding.severity.name, 0) + 1
    summary["finding_counts"] = dict(sorted(counts.items()))
    summary["skipped_rules"] = [rule.rule_id for rule in report.skipped]
    return summary


def build_manifest(
    project_name: str,
    base_fingerprint: str,
    format_version: int,
    variants,
    seed_set,
    validation_report=None,
    path_policy=None,
    overwrite_policy=None,
    format_target=None,
) -> ManifestData:
    """Assemble the manifest content.

    ``variants`` is a sequence of per-variant records; each is an object
    (or mapping) carrying ``key``, ``label``, ``declared_factors``,
    ``applied_edits``, ``file_name``, and ``fingerprint`` — the fields
    plan §13.6 lists. ``format_target`` (the configuration's
    FormatTarget) supplies the version's provenance reference from the
    model — no document is read. Deterministic: input order only, no set
    iteration, no clock.
    """
    selection = getattr(format_target, "version_selection", None)
    evidence = getattr(selection, "evidence", None)
    variant_entries = []
    for variant in variants:
        get = variant.get if isinstance(variant, dict) else (lambda name, v=variant: getattr(v, name))
        variant_entries.append(
            {
                "key": get("key"),
                "label": get("label"),
                "declared_factors": list(get("declared_factors") or ()),
                "applied_edits": list(get("applied_edits") or ()),
                "file_name": get("file_name"),
                "fingerprint": get("fingerprint"),
            }
        )

    data = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "builder_version": _BUILDER_VERSION,
        "project_name": project_name,
        "base_fingerprint": base_fingerprint,
        "format_version": format_version,
        "contract_pin_record": _pin_record_id(format_version, evidence),
        "path_policy": path_policy.name if path_policy is not None else None,
        "overwrite_policy": overwrite_policy.name if overwrite_policy is not None else None,
        "seed_set": list(seed_set),
        "variants": variant_entries,
        "validation_summary": _validation_summary(validation_report),
    }
    return ManifestData(data, run_info())


def run_info() -> dict:
    """The single home of time-varying data (§13.6); excluded from
    determinism assertions."""
    import getpass
    import os
    import platform
    import time

    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "host": platform.node(),
        "user": getpass.getuser(),
        "platform": platform.platform(),
        "pid": os.getpid(),
    }
