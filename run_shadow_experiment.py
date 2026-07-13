#!/usr/bin/env python3
"""Approved fail-closed launcher for the pre-registered no-search shadow experiment."""
import os

os.environ["SHADOW_NO_SEARCH_ENFORCED"] = "1"

from tools.shadow_experiment import main  # noqa: E402


if __name__ == "__main__":
    main()
