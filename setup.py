from setuptools import setup, find_packages

setup(
    name="pkmortality",
    version="0.1.0",
    description=(
        "A Decision-Support Framework for Subnational Mortality "
        "Surveillance in Pakistan -- shared configuration and utilities."
    ),
    packages=find_packages(include=["pkmortality", "pkmortality.*"]),
    python_requires=">=3.10",
    install_requires=[
        "pandas>=2.0",
        "numpy>=1.24",
        "geopandas>=0.14",
        "shapely>=2.0",
        "pyproj>=3.6",
    ],
    extras_require={
        "modeling": [
            "scikit-learn>=1.3",
            "scipy>=1.11",
            "statsmodels>=0.14",
            "pymc>=5.10",
            "arviz>=0.17",
        ],
        "dev": ["pytest>=7.0"],
    },
)
