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

# public/ carries the brand artwork, the loader video, and — the one that is not
# merely cosmetic — pdf.js's worker, which `npm run prebuild` copies out of
# node_modules. Without this line every one of them is a 404: the interface
# renders unbranded and the original-PDF panel cannot start its worker at all.
#
# It is a silent failure in the worst way. `next build` succeeds, the page
# loads, and only the assets are missing, so nothing in CI notices.
COPY --from=build /app/public ./public

RUN useradd --create-home --uid 10002 web && chown -R web:web /app
USER web

EXPOSE 3000
CMD ["npm", "run", "start"]
