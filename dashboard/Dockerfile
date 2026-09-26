FROM node:24-slim AS deps
WORKDIR /app
COPY package.json ./
RUN npm install

FROM node:24-slim AS builder
WORKDIR /app
# next.config.ts's rewrites() (browser-side /v1/* calls, used in dev-compose without Caddy in
# front) is evaluated by `next build` and baked into .next/routes-manifest.json — a runtime
# `environment:` entry in compose.yml has NO effect on it, unlike lib/api.ts's server-component
# fetches, which read process.env fresh per request. Default matches the Docker service name every
# Docker-based deployment (dev-compose or prod) provides; production's own Caddy intercepts /v1/*
# before it ever reaches this rewrite, so baking this in changes nothing there.
ARG BACKEND_INTERNAL_URL=http://api:8000
ENV BACKEND_INTERNAL_URL=$BACKEND_INTERNAL_URL
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:24-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
