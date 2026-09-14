# SPA image: build the React app, then serve it with the nginx that also fronts the API
# (deploy/nginx.conf is mounted over /etc/nginx/conf.d/default.conf by compose).
ARG NODE_IMAGE=node:22-alpine
ARG NGINX_IMAGE=nginx:1.27-alpine

FROM ${NODE_IMAGE} AS builder
ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN --mount=type=cache,target=/pnpm/store pnpm install --frozen-lockfile --filter @better-resume/web...
COPY apps/web apps/web
RUN pnpm --filter @better-resume/web build

FROM ${NGINX_IMAGE}
COPY --from=builder /app/apps/web/dist /usr/share/nginx/html
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
