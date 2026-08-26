"""
Central configuration: paths, constants, and canonical naming rules.

Every script in this project imports paths from here rather than
hardcoding them, so the pipeline can be relocated or re-run from a
single entry point (see scripts/run_pipeline.sh).
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent

DATA_RAW = ROOT / "data" / "raw"
DATA_EXTERNAL = ROOT / "data" / "external"
DATA_PROCESSED = ROOT / "data" / "processed"

PBS2017_DIR = DATA_RAW / "pbs2017-main" / "data"
SHAPEFILE_DIR = PBS2017_DIR / "00_shapefiles"

MODELS_DIR = ROOT / "models"
FIGURES_DIR = ROOT / "figures"
DOCS_DIR = ROOT / "docs"

for _p in [DATA_PROCESSED, DATA_EXTERNAL, MODELS_DIR, FIGURES_DIR]:
    _p.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Coordinate reference system
# ---------------------------------------------------------------------------
CRS_WGS84 = "EPSG:4326"          # lat/lon, for web maps
CRS_PAKISTAN_EQUAL_AREA = "EPSG:24313"  # Pakistan grid zone, for area/distance calcs

# ---------------------------------------------------------------------------
# Canonical district key
# ---------------------------------------------------------------------------
# PBS census tables label districts as "ABBOTTABAD DISTRICT" (upper case,
# suffixed). The shapefile crosswalk (shapefile_link.csv) uses the same
# convention in its `pbs_name` column. We standardize everything to this
# upper-case "<NAME> DISTRICT" form internally and only prettify for display
# in the dashboard/paper layer.


def standardize_district_name(name: str) -> str:
    """Normalize a district name string to the canonical PBS key form."""
    if name is None:
        return name
    n = str(name).strip().upper()
    n = " ".join(n.split())  # collapse whitespace
    if not n.endswith("DISTRICT"):
        n = f"{n} DISTRICT"
    # common census-vs-shapefile spelling divergences
    fixes = {
        "SHAHEED BENAZIRABAD DISTRICT": "SHAHEED BENAZIRABAD DISTRICT",
        "D.G. KHAN DISTRICT": "DERA GHAZI KHAN DISTRICT",
        "D. G. KHAN DISTRICT": "DERA GHAZI KHAN DISTRICT",
        "D.I. KHAN DISTRICT": "DERA ISMAIL KHAN DISTRICT",
        "D. I. KHAN DISTRICT": "DERA ISMAIL KHAN DISTRICT",
    }
    return fixes.get(n, n)


def prettify_district_name(name: str) -> str:
    """Convert canonical key back to a display-friendly title case name."""
    if name is None:
        return name
    n = str(name).replace(" DISTRICT", "").strip()
    return n.title()


# ---------------------------------------------------------------------------
# Modeling constants
# ---------------------------------------------------------------------------
RANDOM_SEED = 42
N_BOOTSTRAP = 1000

# Under-5 mortality proxy: WHO/UNICEF-style scale (deaths per 1,000 live
# births) used only for interpretability of the *proxy* risk score before
# real PDHS-derived U5MR is substituted in.
U5MR_SCALE_PER = 1000
