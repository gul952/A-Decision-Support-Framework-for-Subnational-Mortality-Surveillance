"""
pkmortality: A Decision-Support Framework for Subnational Mortality
Surveillance in Pakistan.

Package layers:
    cleaning   -- ingest and standardize raw public data sources
    features   -- construct district-level indicators from cleaned data
    models     -- small-area estimation (SAE) of mortality risk
    decision   -- prioritization / decision engine for surveillance targeting

See docs/DATA_SOURCES.md for provenance of every input, and
docs/LIMITATIONS.md for what this framework does and does not claim.
"""

__version__ = "0.1.0"
