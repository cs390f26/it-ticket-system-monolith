from setuptools import find_packages, setup

setup(
    name="tickets",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    py_modules=["db"],
    python_requires=">=3.12",
)
