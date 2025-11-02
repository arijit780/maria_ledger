# setup.py
from setuptools import setup, find_packages

setup(
    name="maria-ledger",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pyyaml",
        "typer",
        "tabulate",
        "mysql-connector-python",
        "cryptography",
        "datetime",
        "rich",
    ],
    entry_points={
        "console_scripts": [
            "maria-ledger = maria_ledger.cli.main:main",
            "maria_ledger = maria_ledger.cli.main:main"
        ]
    },
)
