"""Shared pytest fixtures for evlos-safety tests."""
import sys
from pathlib import Path

# Make 'backend' importable as the package root for tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
