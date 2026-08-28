"""Shared property-catalog database identities.

Keep the production identity in one lightweight module so readers and writers
cannot silently diverge when the deployment database name changes.
"""

from __future__ import annotations

PRODUCTION_PROPERTY_CATALOG_DATABASE = "property_catalog"


def is_production_property_catalog_database(database: str) -> bool:
    """Return whether ``database`` is the canonical production catalog."""

    return database == PRODUCTION_PROPERTY_CATALOG_DATABASE


__all__ = [
    "PRODUCTION_PROPERTY_CATALOG_DATABASE",
    "is_production_property_catalog_database",
]
