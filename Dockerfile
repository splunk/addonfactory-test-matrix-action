# Container image that runs your code
FROM python:3.11.2 as base
ENV PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    PYTHONUNBUFFERED=1

FROM base as builder
ENV PIP_DEFAULT_TIMEOUT=100 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.0.5

RUN pip install "poetry"
RUN python -m venv /venv
COPY pyproject.toml poetry.lock ./
RUN poetry export -f requirements.txt | pip install -r /dev/stdin
COPY . .
RUN poetry build && . /venv/bin/activate; pip install dist/*.whl

FROM base as final

COPY /entrypoint.sh /
COPY --from=builder /venv /venv

WORKDIR /github/workspace
ENTRYPOINT ["/entrypoint.sh"]
