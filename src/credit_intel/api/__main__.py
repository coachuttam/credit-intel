"""``python -m credit_intel.api [--config SETTINGS_TOML]`` (and ``credit-intel-api``): start the service (PRD FR-016, SEC-15).
``python -m credit_intel.api prune --older-than DAYS [--dry-run]`` clears old run folders, cache entries and upload directories (PRD SEC-18, OD-40).

The host is checked first (resident memory must be readable), then the settings, then the container's memory limit against the pool (FR-018 criterion 7). A missing limit, a relative folder, a bad token, or a host that is not a loopback address with no token set stops the
service before it listens, with the catalogued ``E-CONFIG-INVALID`` and the exit code of the command line (6).
"""

import argparse
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import IO, Any

from credit_intel.api.retention import prune, render
from credit_intel.api.sizing import check_container_memory, container_memory_limit_mb
from credit_intel.config import DEFAULT_SETTINGS_PATH, load_api_settings, load_parse_limits
from credit_intel.ingestion.errors import EXIT_OK, IngestionError, exit_code
from credit_intel.ingestion.sandbox import check_memory_measurement


def _serve(app: Any, host: str, port: int) -> None:
    import uvicorn

    # One access line comes from the service itself (without anything the client sent); the server's own would repeat the raw request line.
    # `proxy_headers=False`: the server's own reading of forwarded addresses is off; the only trust in a proxy is `api.trusted_proxies`, read by the service itself.
    uvicorn.run(app, host=host, port=port, access_log=False, server_header=False, proxy_headers=False)


def prune_main(argv: Sequence[str], *, env: Mapping[str, str] | None = None, stdout: IO[str] | None = None, stderr: IO[str] | None = None,
               now: Callable[[], datetime] | None = None) -> int:  # fmt: skip
    """``credit-intel-api prune --older-than DAYS [--dry-run] [--config SETTINGS_TOML]`` (PRD SEC-18, OD-40): remove whole run folders, cache entries and upload
    directories older than DAYS. DAYS is required and has no default. Nothing is removed with ``--dry-run``. It reads the same settings file as the service (for the two folders)."""
    import os

    out, err = stdout or sys.stdout, stderr or sys.stderr
    parser = argparse.ArgumentParser(prog="credit-intel-api prune", description="Remove old run folders, cache entries and upload directories. Whole folders only; the service never does this by itself.")
    parser.add_argument("--older-than", type=int, required=True, metavar="DAYS", help="remove what is at least this many days old (a whole number, at least 1; no default)")
    parser.add_argument("--dry-run", action="store_true", help="list what would be removed and remove nothing")
    parser.add_argument("--config", type=Path, default=DEFAULT_SETTINGS_PATH, metavar="SETTINGS_TOML", help="settings file (default: config/settings.toml)")
    args = parser.parse_args(list(argv))
    if args.older_than < 1:
        parser.error("--older-than must be a whole number of days, at least 1")
    try:
        settings = load_api_settings(args.config, os.environ if env is None else env)
    except IngestionError as error:
        print(str(error), file=err)
        return exit_code(error)
    for line in render(prune(settings, args.older_than, dry_run=args.dry_run, now=now)):
        print(line, file=out)
    return EXIT_OK


def main(argv: Sequence[str] | None = None, *, env: Mapping[str, str] | None = None, stderr: IO[str] | None = None, stdout: IO[str] | None = None,
         serve: Callable[[Any, str, int], None] = _serve, check_memory: Callable[[], None] = check_memory_measurement,
         container_limit: Callable[[], int | None] = container_memory_limit_mb) -> int:  # fmt: skip
    import os

    from credit_intel.api.app import create_app

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ["prune"]:
        return prune_main(arguments[1:], env=env, stdout=stdout, stderr=stderr)
    err = stderr or sys.stderr
    parser = argparse.ArgumentParser(prog="credit-intel-api", description="Serve the credit memo pipeline over HTTP. A draft for human review, not a credit decision.")
    parser.add_argument("--config", type=Path, default=DEFAULT_SETTINGS_PATH, metavar="SETTINGS_TOML", help="settings file (default: config/settings.toml)")
    args = parser.parse_args(arguments)
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
