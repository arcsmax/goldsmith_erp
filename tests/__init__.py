"""Test suite root package.

Makes ``tests`` an importable package so modules can use absolute imports
such as ``from tests.integration.conftest import ...`` regardless of how
pytest is invoked (plain ``pytest`` vs. ``python -m pytest``). Without this
file those imports raise ``ModuleNotFoundError: No module named 'tests'``
under pytest's default ``prepend`` import mode.
"""
