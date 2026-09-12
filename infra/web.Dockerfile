# The reader interface: a production Next.js build, not a dev server.
#
# A dev server would start faster and reload on edit, and would also hide every
# problem that only appears in a production build. CLAUDE.md asks for the
# frontend production build to be validated; running the real thing here is how
# that stays true rather than being a CI job nobody looks at.

FROM node:22-slim AS build

WORKDIR /app

# Dependencies first, so editing a component does not reinstall them.
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

COPY apps/web ./

# NEXT_PUBLIC_* is inlined at build time, not read at run time, so the API
# address has to be known now. It is the address the **browser** will use, which
# is the host's, not a compose service name: the page runs on somebody's laptop,
# not inside this network.
ARG NEXT_PUBLIC_READER_API=http://127.0.0.1:8000
ENV NEXT_PUBLIC_READER_API=$NEXT_PUBLIC_READER_API

RUN npm run build

FROM node:22-slim

ENV NODE_ENV=production
WORKDIR /app

COPY --from=build /app/package.json /app/package-lock.json ./
RUN npm ci --omit=dev

COPY --from=build /app/.next ./.next
COPY --from=build /app/next.config.mjs ./next.config.mjs

# No `COPY public`: this app has no public/ directory, and COPY fails on a path
# that does not exist rather than skipping it. Add one back here if static
# assets ever land there — a missing favicon is a silent 404, not a build error.

RUN useradd --create-home --uid 10002 web && chown -R web:web /app
USER web

EXPOSE 3000
CMD ["npm", "run", "start"]
