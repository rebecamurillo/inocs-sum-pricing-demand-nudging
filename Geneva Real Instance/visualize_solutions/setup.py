from setuptools import setup, find_packages

setup(
    name="visualize_solutions",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "geopandas",
        "folium",
        "ipywidgets",
        "IPython",
        "shapely",
        "pandas",
        "numpy"
    ],
)
