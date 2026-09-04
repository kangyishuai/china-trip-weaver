"""Deterministic Trip HTML renderer and validator."""

from .html import RendererError, render_trip, safe_output_name
from .validate_html import HTMLValidationReport, validate_html


def render_journey(*args, **kwargs):
    from .journey_html import render_journey as implementation

    return implementation(*args, **kwargs)


def validate_journey_html(*args, **kwargs):
    from .validate_journey_html import validate_journey_html as implementation

    return implementation(*args, **kwargs)

__all__ = [
    "RendererError",
    "render_trip",
    "render_journey",
    "safe_output_name",
    "HTMLValidationReport",
    "validate_html",
    "validate_journey_html",
]
