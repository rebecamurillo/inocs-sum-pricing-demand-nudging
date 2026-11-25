# Build context: the repository root (the image needs sum_nsm_dynamic_pricing/ and demo/api/).
#   docker build -f demo/api/Dockerfile -t pricing-demo-api:dev .
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# The layout matches the repository: pyproject.toml refers to ../../sum_nsm_dynamic_pricing.
WORKDIR /app
COPY sum_nsm_dynamic_pricing ./sum_nsm_dynamic_pricing
COPY demo/api/pyproject.toml demo/api/uv.lock demo/api/.python-version ./demo/api/

# The dependencies come first and change rarely, so an edit of the API's source does not
# install pandas, geopandas and gurobipy again.
WORKDIR /app/demo/api
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY demo/api/alembic.ini ./
COPY demo/api/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

RUN useradd --system --create-home app
USER app

EXPOSE 8100

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn pricing_demo.asgi:app --host 0.0.0.0 --port 8100"]
