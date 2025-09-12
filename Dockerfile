FROM python:3.11-alpine as base

ENV PYTHONFAULTHANDLER=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONHASHSEED=random \
  PIP_NO_CACHE_DIR=off \
  PIP_DISABLE_PIP_VERSION_CHECK=on \
  PIP_DEFAULT_TIMEOUT=100

USER 0
RUN apk update && \
    apk add curl && \
    apk upgrade

FROM base as builder

ENV VENV_PATH="poetry_venv" \
    POETRY_VERSION="1.8.4" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    PATH="/root/.local/bin:$PATH"

RUN curl -sSL https://install.python-poetry.org | python - && \
    ln -s /root/.local/bin/poetry /usr/local/bin/poetry

WORKDIR /app

COPY README.md pyproject.toml poetry.lock ./
RUN poetry env use 3.11 && \
    poetry install --without dev --no-interaction --no-ansi --no-root

COPY src/ ./src/
RUN poetry build -f wheel
RUN poetry run pip install dist/*.whl

FROM base AS final

WORKDIR /app
COPY src/ /app/src/

# switch back to a non-root user for executing
USER 1001

ENV PATH="/app/.venv/bin:$PATH"
COPY --from=builder /app/.venv /app/.venv

CMD []
