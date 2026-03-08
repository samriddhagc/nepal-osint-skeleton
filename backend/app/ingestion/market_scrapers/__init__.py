"""Market data scrapers for Nepal financial data."""
from app.ingestion.market_scrapers.nrb_forex import fetch_nrb_forex
from app.ingestion.market_scrapers.gold_silver import fetch_gold_silver_prices
from app.ingestion.market_scrapers.fuel_prices import fetch_fuel_prices
from app.ingestion.market_scrapers.nepse import fetch_nepse_index

__all__ = [
    "fetch_nrb_forex",
    "fetch_gold_silver_prices",
    "fetch_fuel_prices",
    "fetch_nepse_index",
]
