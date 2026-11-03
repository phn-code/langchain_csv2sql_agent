FROM node:24-alpine AS build
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
# Vite inlines VITE_* at build time, so the API URLs are fixed per image.
ARG VITE_API_URL=http://localhost:2024
ARG VITE_DATA_API_URL=http://localhost:8000
ARG VITE_ASSISTANT_ID=agent
ENV VITE_API_URL=$VITE_API_URL VITE_DATA_API_URL=$VITE_DATA_API_URL VITE_ASSISTANT_ID=$VITE_ASSISTANT_ID
RUN pnpm build

FROM nginxinc/nginx-unprivileged:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
