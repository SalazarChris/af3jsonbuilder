"""The Qt desktop front end (Stage 1: review & preview).

A second **render** layer beside the console menu: it draws the jobs,
validation findings and generated JSON the existing application services
already produce, and it decides nothing itself. It lives under
``ui/render`` because that is the family the architecture rules already
grant the right to reach ``app`` and ``ui/present`` — a sibling top-level
package would need the layout and dependency tests rewritten first.

Requires the optional ``gui`` extra (PySide6). Importing this package
imports Qt; the console application and its test suite do not.

Nothing in this package mutates a job, allocates an identifier, builds a
wire document or writes a file.
"""

from __future__ import annotations

from configbuilder.ui.render.qt.application import main

__all__ = ["main"]
