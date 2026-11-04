# Build from the repository root: docker build -f apps/web/Dockerfile -t ai-shield-web .
FROM oven/bun:1.4 AS build
WORKDIR /repo
COPY package.json bun.lock ./
COPY apps/web/package.json apps/web/package.json
RUN bun install --frozen-lockfile --ignore-scripts
COPY apps/web apps/web
COPY contracts contracts
RUN cd apps/web && bunx nuxt prepare && bun run build

FROM node:24-slim
WORKDIR /app
COPY --from=build /repo/apps/web/.output ./.output
USER node
ENV PORT=3000 NUXT_PUBLIC_API_BASE_URL=http://localhost:8000
EXPOSE 3000
CMD ["node", ".output/server/index.mjs"]
