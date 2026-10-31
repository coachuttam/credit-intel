# The container image of AI Credit Intelligence (PRD FR-018, v0.4.62; Phase 7 step 2).
#
# Build it with deploy/build.sh, which resolves the commit and checks the inputs. By hand:
#   docker build --build-arg PYTHON_IMAGE=<base image pinned by digest> --build-arg BUILD_COMMIT=<40-hex commit> -t credit-intel:<commit> .
#
# * The base image is an argument with NO default, and the build stops unless it is pinned by digest (SEC-11).
# * Named paths only are copied (criterion 1); .dockerignore keeps everything else out of the context (criterion 2).
# * The final image holds no build tools, no tests, no secret and no data. It runs as a non-root user (criterion 3).
# * `--target test` makes a separate image with the dev tools and the tests, for the in-image checks of criterion 10 (the golden, reproducibility, service, API,
#   parse-limit and OCR-engine tests; the tests that read the README or the PRD are not in it). It is not the product.

ARG PYTHON_IMAGE

# ---- the base: the pinned image, checked -------------------------------------------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS base
ARG PYTHON_IMAGE
RUN case "${PYTHON_IMAGE}" in *@sha256:????????????????????????????????????????????????????????????????) ;; *) \
      echo "PYTHON_IMAGE must be pinned by digest (name@sha256:<64 hex>); see docs/RUNBOOK_container.md" >&2; exit 1 ;; esac

# ---- the environment, built from the lock file ---------------------------------------------------------------------------------------------------------
FROM base AS builder
ARG UV_VERSION=0.12.6
RUN pip install --no-cache-dir "uv==${UV_VERSION}"
WORKDIR /app
COPY pyproject.toml uv.lock ./
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv sync --frozen --no-dev --no-install-project --python /usr/local/bin/python
ENV UV_PROJECT_ENVIRONMENT=/opt/venv-dev
RUN uv sync --frozen --no-install-project --python /usr/local/bin/python
# The tests start fresh interpreters (`-I`, `-m credit_intel.api`) that see no PYTHONPATH, and the project itself is not installed (--no-install-project):
# a .pth file in the DEV environment only, as an editable install would leave, makes the package importable there. The product environment gets none.
RUN /opt/venv-dev/bin/python -c "import sysconfig; print(sysconfig.get_paths()['purelib'])" > /tmp/purelib \
 && echo /app/src > "$(cat /tmp/purelib)/credit_intel_src.pth" && rm /tmp/purelib

# ---- the product ------------------------------------------------------------------------------------------------------------------------------------
FROM base AS runtime
ARG BUILD_COMMIT
RUN case "${BUILD_COMMIT}" in [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;; *) \
      echo "BUILD_COMMIT must be a full lower-case 40-hex commit" >&2; exit 1 ;; esac
RUN apt-get update \
 && apt-get install --no-install-recommends -y tesseract-ocr tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin app \
 && mkdir -p /data/runs /data/cache /config \
 && chown 10001:10001 /data/runs /data/cache
COPY --from=builder /opt/venv /opt/venv
COPY src /app/src
COPY prompts /app/prompts
COPY config /app/config
COPY tests/eval/assignments.jsonl /app/tests/eval/assignments.jsonl
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CREDIT_INTEL_BUILD_COMMIT=${BUILD_COMMIT} \
    CREDIT_INTEL_API_OUTPUT_DIR=/data/runs \
    CREDIT_INTEL_API_CACHE_DIR=/data/cache \
    CREDIT_INTEL_API_HOST=0.0.0.0 \
    TMPDIR=/tmp
WORKDIR /app
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"]
ENTRYPOINT ["python", "-m", "credit_intel.api"]
CMD ["--config", "/config/settings.toml"]

# ---- the tests, for the checks inside the image (not the product) ------------------------------------------------------------------------------
FROM runtime AS test
COPY --from=builder /opt/venv-dev /opt/venv-dev
COPY tests /app/tests
COPY pyproject.toml /app/pyproject.toml
ENV PATH=/opt/venv-dev/bin:$PATH
ENTRYPOINT ["python", "-m", "pytest"]
CMD ["tests/unit/test_fresh_process_golden.py", "tests/integration/test_reproducibility.py", "tests/integration/test_results_json.py", \
     "tests/integration/test_service.py", "tests/integration/test_api.py", "tests/integration/test_api_end_to_end.py", \
     "tests/unit/test_parse_limits.py", "tests/unit/test_parse_limits_engine.py", "tests/unit/test_memory_reading.py", \
     "tests/unit/test_child_environment.py", "tests/unit/test_tesseract_ocr.py", "tests/unit/test_container_sizing.py", \
     "-q", "-p", "no:cacheprovider"]

# ---- the last stage, so that a bare `docker build .` builds the product and not the test image -------------------------------------------------
FROM runtime AS product
