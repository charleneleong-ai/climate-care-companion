# The whole stack in one image.
#
# Next.js is the only thing exposed. The Python core listens on loopback and is
# unreachable from outside the container, which is what the architecture already
# assumed — `assess-client.ts` calls CORE_API_URL server-side and never ships it
# to the browser. So the split survives deployment instead of needing two hosts.
#
# Built for Hugging Face Spaces, which serves whatever listens on 7860 and runs
# the container as uid 1000. Nothing here is Spaces-specific beyond that port, so
# Fly or Render take the same image with --build-arg PORT.

FROM node:22-slim AS web
WORKDIR /build

# Dependencies first, so a source-only change does not re-resolve npm.
COPY web/app/package.json web/app/package-lock.json ./
RUN npm ci

COPY web/app/ ./
# Compiled into the bundle at build time, so it must be present now rather than
# injected at run time like the server-side secrets.
ARG NEXT_PUBLIC_VAPID_PUBLIC_KEY=""
ENV NEXT_PUBLIC_VAPID_PUBLIC_KEY=${NEXT_PUBLIC_VAPID_PUBLIC_KEY}
RUN npm run build


FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PORT=7860 \
    CORE_API_URL=http://127.0.0.1:8000 \
    CLIMATISE_PUSH_STORE=/data/climatise-push.json

# Node is needed at run time too — `next start` serves the built app.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9.29 /uv /usr/local/bin/uv

WORKDIR /app

# The workspace resolves from the lockfile, so every member's pyproject.toml has
# to land before `uv sync` — copying only the root would fail resolution.
COPY pyproject.toml uv.lock ./
COPY packages/ ./packages/
COPY services/ ./services/
RUN uv sync --frozen --no-dev

# Runtime data the core reads: persona YAML, the reason/action corpus, templates.
COPY data/ ./data/

COPY --from=web /build/.next ./web/app/.next
COPY --from=web /build/public ./web/app/public
COPY --from=web /build/node_modules ./web/app/node_modules
COPY --from=web /build/package.json ./web/app/package.json
COPY --from=web /build/next.config.mjs ./web/app/next.config.mjs

# Spaces runs as uid 1000 and only /data is writable. Without this the push
# subscription store cannot be written and every registration fails.
RUN mkdir -p /data && chown -R 1000:1000 /data /app
USER 1000

COPY --chown=1000:1000 docker-entrypoint.sh /app/
EXPOSE 7860
CMD ["/app/docker-entrypoint.sh"]
