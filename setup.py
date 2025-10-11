from setuptools import setup, find_packages

setup(
    name="maria-ledger",
    version="0.1.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "mysql-connector-python",
        "pyyaml",
    ],
    python_requires=">=3.8",
)
