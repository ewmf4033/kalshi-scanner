#!/usr/bin/env python3
"""Approved root entrypoint for the pre-registered no-search shadow experiment."""

from tools import shadow_experiment as experiment


_legacy_build_scanner_prompt = experiment.build_scanner_prompt


def _build_no_search_track_a_prompt(markets_json: str) -> str:
    """Preserve Track A price visibility while removing external-search instructions."""
    prompt = _legacy_build_scanner_prompt(markets_json)
    prompt = prompt.replace(
        "Use search to find grounding data: CME FedWatch, Cleveland Fed Nowcast, NOAA, BLS, polling aggregators, institutional research",
        "Do not use external search, browsing, retrieval, tools, or external APIs. Forecast only from the supplied contract data and internal knowledge.",
    )
    return prompt


# Enforce the pre-registered no-search rule for all Track A calls launched here.
experiment.build_scanner_prompt = _build_no_search_track_a_prompt


if __name__ == "__main__":
    experiment.main()
