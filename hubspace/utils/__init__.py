"""Generic, dependency-free helper functions shared across hub.

Pure utilities only — no hub domain logic, no module-level state.
"""
from .paths import env_path, is_within
from .text import esc_html, relative_time, slugify

__all__ = ["env_path", "is_within", "esc_html", "relative_time", "slugify"]
