"""``python -m credit_intel.api [--config SETTINGS_TOML]`` (and ``credit-intel-api``): start the service (PRD FR-016, SEC-15).

The host is checked first (resident memory must be readable), then the settings, then the container's memory limit against the pool (FR-018 criterion 7). A missing limit, a relative folder, a bad token, or a host that is not a loopback address with no token set stops the
service before it listens, with the catalogued ``E-CONFIG-INVALID`` and the exit code of the command line (6).
"""

import argparse
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import IO, Any

from credit_intel.api.sizing import check_container_memory, container_memory_limit_mb
from credit_intel.config import DEFAULT_SETTINGS_PATH, load_api_settings, load_parse_limits
from credit_intel.ingestion.errors import EXIT_OK, IngestionError, exit_code
from credit_intel.ingestion.sandbox import check_memory_measurement


def _serve(app: Any, host: str, port: int) -> None:
    import uvicorn

    # One access line comes from the service itself (without anything the client sent); the server's own would repeat the raw request line.
    uvicorn.run(app, host=host, port=port, access_log=False, server_header=False)


def main(argv: Sequence[str] | None = None, *, env: Mapping[str, str] | None = None, stderr: IO[str] | None = None,
         serve: Callable[[Any, str, int], None] = _serve, check_memory: Callable[[], None] = check_memory_measurement,
         container_limit: Callable[[], int | None] = container_memory_limit_mb) -> int:  # fmt: skip
    import os

    from credit_intel.api.app import create_app

    err = stderr or sys.stderr
    parser = argparse.ArgumentParser(prog="credit-intel-api", description="Serve the credit memo pipeline over HTTP. A draft for human review, not a credit decision.")
    parser.add_argument("--config", type=Path, default=DEFAULT_SETTINGS_PATH, metavar="SETTINGS_TOML", help="settings file (default: config/settings.toml)")
    args = parser.parse_args(argv)
    environment = os.environ if env is None else env
    try:
        check_memory()  # the parse limits are measured, not assumed: a host that cannot be measured does not start (SEC-12, Phase 7 step 1)
        settings = load_api_settings(args.config, environment)
        check_container_memory(settings, load_parse_limits(args.config, environment), container_limit())  # a container too small for the pool is refused (FR-018 criterion 7)
        app = create_app(settings, config=args.config, env=environment)
    except IngestionError as error:
        print(str(error), file=err)
        return exit_code(error)
    serve(app, settings.host, settings.port)
    return EXIT_OK


def run() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    run()
