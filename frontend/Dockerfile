FROM node:23 AS development
WORKDIR /app
ENV NODE_ENV development
RUN corepack enable
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
EXPOSE 3000
CMD ["pnpm", "dev"]

# Stage 0, "build-stage", based on Node.js, to build and compile the frontend
FROM node:23 AS build-stage

ARG NEXT_PUBLIC_BACKEND_URL
ENV NEXT_PUBLIC_BACKEND_URL=${NEXT_PUBLIC_BACKEND_URL}

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

RUN pnpm run build

# Stage 1, "run-stage", to serve the Next.js application
FROM node:23-alpine AS run-stage

WORKDIR /app

ARG BACKEND_URL
ENV BACKEND_URL=${BACKEND_URL}
ENV NODE_ENV=production

RUN corepack enable

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --prod --frozen-lockfile

COPY --from=build-stage /app/public ./public
COPY --from=build-stage /app/.next ./.next
COPY --from=build-stage /app/next.config.ts .

EXPOSE 3000

CMD ["pnpm", "start"]
