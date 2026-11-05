# syntax=docker/dockerfile:1
#
# atomc container image (PLAN.md §5.1).
#
#   docker build -f docker/Dockerfile --target base   -t atomc:base   .
#   docker build -f docker/Dockerfile --target kernels -t atomc:kernels .
#   docker build -f docker/Dockerfile --target atomc  -t atomc:latest  .
#
# `base` is small and fast (tooling only); `kernels` adds the heavy hardware
# toolchains (Renode, arm-none-eabi-gcc, QMK, build123d/OCP); `atomc` layers the
# checked-out repo on top. CI builds `base` on PRs and the full `atomc` image on
# `v*` tags (see .github/workflows/docker.yml).

ARG NODE_VERSION=22
ARG UV_VERSION=0.13.7
ARG RENODE_VERSION=1.17.0
ARG PYTHON_VERSION=3.14

# Source images for the toolchain we copy into `base`. BuildKit does not allow
# ARG expansion in `--from`, so they are declared as (unused) stages.
FROM node:${NODE_VERSION}-bookworm-slim AS node
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# ---------------------------------------------------------------------------
# base: debian bookworm-slim + uv + node + pnpm
# ---------------------------------------------------------------------------
FROM debian:bookworm-slim AS base

ARG DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH=/usr/local/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        jq \
        make \
        unzip \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

# Node.js 22 (official image ships a matching bookworm build; copy it in).
COPY --from=node /usr/local /usr/local

# uv / uvx.
COPY --from=uv /uv /uvx /usr/local/bin/

# pnpm (kept in sync with package.json#packageManager).
RUN npm install --global pnpm@10.30.3

RUN useradd --create-home --uid 1000 atomc
WORKDIR /home/atomc

# ---------------------------------------------------------------------------
# kernels: Renode, arm-none-eabi-gcc, QMK CLI, python 3.14 hardware kernels
# ---------------------------------------------------------------------------
FROM base AS kernels

ARG PYTHON_VERSION
ARG RENODE_VERSION
ARG DEBIAN_FRONTEND=noninteractive
USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        binutils-arm-none-eabi \
        gcc-arm-none-eabi \
        libicu72 \
        libnewlib-arm-none-eabi \
        libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Renode linux-portable (self-contained .NET runtime).
RUN set -eux; \
    curl -fsSL -o /tmp/renode.tar.gz \
      "https://github.com/renode/renode/releases/download/v${RENODE_VERSION}/renode-${RENODE_VERSION}.linux-portable.tar.gz"; \
    tar -xzf /tmp/renode.tar.gz -C /opt; \
    mv "/opt/renode_${RENODE_VERSION}-portable" /opt/renode; \
    ln -s /opt/renode/renode /usr/local/bin/renode; \
    rm /tmp/renode.tar.gz

# QMK CLI (installed globally; a qmk_firmware checkout is mounted at runtime).
ENV UV_TOOL_BIN_DIR=/usr/local/bin \
    UV_TOOL_DIR=/opt/uv-tools
RUN uv tool install qmk

# Hardware Python kernels in their own venv (OCP is not thread-safe; the daemon
# runs CAD in a dedicated worker process, not here).
ENV ATOMC_VENV=/opt/atomc-venv
RUN uv venv --python "${PYTHON_VERSION}" "${ATOMC_VENV}" \
    && uv pip install --python "${ATOMC_VENV}/bin/python" \
        "build123d==0.13.0" \
        "cadquery-ocp==8.0.1.1.0" \
        "kiutils==1.4.8" \
        "trimesh==5.2.0"
ENV VIRTUAL_ENV=${ATOMC_VENV} \
    PATH=${ATOMC_VENV}/bin:$PATH

USER atomc

# ---------------------------------------------------------------------------
# atomc: the repo itself, with all workspace deps installed
# ---------------------------------------------------------------------------
FROM kernels AS atomc

USER atomc
WORKDIR /home/atomc/atomc
COPY --chown=atomc:atomc . .

RUN uv sync --all-packages \
    && pnpm install --frozen-lockfile \
    && pnpm build

CMD ["bash"]
