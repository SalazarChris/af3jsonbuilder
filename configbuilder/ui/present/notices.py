"""Consequence notices shared by both front ends.

A confirmation is only useful when it names what the confirmed action will
actually remove. ``remove_record`` deletes a DNA duplex as one entity and a
multi-copy ligand as all of its identifiers, and the console used to ask
``Delete "A"?`` for both — naming one record while removing two.

The wording lives here, once, so the desktop's confirmation and the console's
confirmation cannot describe the same action differently. Nothing here decides
what a deletion does: the caller passes the facts it already holds (the
service's own identifiers and the model's ``duplex_partner`` answer).
"""

from __future__ import annotations

from configbuilder.ui.present.strings import text as _text

__all__ = ["removal_notice"]


def removal_notice(identifiers: str, partner_key=None, copy_count: int = 1) -> str:
    """The question to ask before removing a record.

    ``identifiers`` is the record's own identifier text as the front end
    displays it, ``partner_key`` the duplex partner's identifier (``None``
    when the strand has no partner) and ``copy_count`` the number of
    identifiers the record holds.
    """
    if partner_key:
        return _text("gui.delete_duplex") % (identifiers, partner_key)
    if copy_count > 1:
        return _text("gui.delete_copies") % (identifiers, copy_count)
    return _text("gui.delete_single") % identifiers
