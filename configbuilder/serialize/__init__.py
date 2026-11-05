"""Serialization (IMPLEMENTATION_PLAN.md §11): one function, one encoding
policy. See ``encode.py`` for the policy and its rationale."""

from configbuilder.serialize.encode import EncodeError, encode, encode_to_file

__all__ = ["EncodeError", "encode", "encode_to_file"]
