"""Runs the pipeline on a PDF with a scripted reply and writes results.json to standard output (used by the fresh-process test).

``python results_child.py <pdf> <reply.json> <cache_dir>``. Not a test module.
"""

import sys
from pathlib import Path

from credit_intel.config import LLMSettings
from credit_intel.export.results import render_results
from credit_intel.llm.provider import FakeProvider
from credit_intel.run import run_pipeline

pdf, reply, cache = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
settings = LLMSettings(provider="fake", model_id="m", token_ceiling=1_000_000, max_output_tokens=2000)
result = run_pipeline(pdf, FakeProvider(script=[reply.read_text(encoding="utf-8")]), settings, cache_dir=cache)
sys.stdout.buffer.write(render_results(result.extraction, result.metrics, result.rules, result.profile).encode("utf-8"))
