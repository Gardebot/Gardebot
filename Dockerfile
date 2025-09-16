FROM python:3.11-alpine AS base

ENV PYTHONFAULTHANDLER=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONHASHSEED=random \
  PIP_NO_CACHE_DIR=off \
  PIP_DISABLE_PIP_VERSION_CHECK=on \
  PIP_DEFAULT_TIMEOUT=100

RUN apk update && \
    apk add --no-cache bash ca-certificates curl gnupg shadow && \
    apk upgrade

FROM base AS builder

ENV VENV_PATH="poetry_venv" \
    POETRY_VERSION="1.8.4" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    PATH="/root/.local/bin:$PATH"

RUN curl -sSL https://install.python-poetry.org | python - && \
    ln -s /root/.local/bin/poetry /usr/local/bin/poetry
ADD https://packages.doppler.com/public/cli/rsa.8004D9FF50437357.key /etc/apk/keys/cli@doppler-8004D9FF50437357.rsa.pub
RUN echo 'https://packages.doppler.com/public/cli/alpine/any-version/main' | tee -a /etc/apk/repositories && \
    apk add doppler

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
RUN chown -R 1001:0 /app

# switch back to a non-root user for executing
USER 1001

ENV PATH="/app/.venv/bin:$PATH"
ENV HOME=/app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /usr/bin/doppler /usr/bin/doppler

ENTRYPOINT ["doppler", "run", "--config-dir", "/app/.doppler", "--"]
CMD ["python", "-m", "gardebot.app"]
