"""Source adapters for signal ingestion."""

from app.ingestion.adapters.crunchbase_adapter import CrunchbaseAdapter
from app.ingestion.adapters.producthunt_adapter import ProductHuntAdapter
from app.ingestion.adapters.test_adapter import TestAdapter

__all__ = ["CrunchbaseAdapter", "ProductHuntAdapter", "TestAdapter"]
