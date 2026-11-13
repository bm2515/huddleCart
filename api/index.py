"""Vercel entry point: serves the FastAPI agent from agent/huddlecart."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))

from huddlecart.api import app  # noqa: E402,F401
