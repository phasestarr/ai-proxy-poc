# Purpose:
# - Build and package the frontend application for containerized execution.
#
# Current responsibilities:
# - Install Node dependencies
# - Build the Vite application
# - Serve the built static files through NGINX
#
# Notes:
# - Version pins are supplied through Docker build args from the repo-root .env.
# - Keep the image small and predictable.
# - Separate dependency installation from source copy when possible for caching.

ARG NODE_VERSION
ARG NGINX_VERSION

FROM node:${NODE_VERSION}-alpine AS build

ARG NODE_VERSION
ARG NPM_VERSION

WORKDIR /app

RUN npm install -g npm@${NPM_VERSION}

COPY package*.json ./
RUN npm ci

COPY . .
RUN test -n "$NODE_VERSION" && test -n "$NPM_VERSION"
RUN npm run build

FROM nginx:${NGINX_VERSION} AS runtime

ARG NGINX_VERSION
RUN test -n "$NGINX_VERSION"

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx/default.conf /etc/nginx/templates/default.conf.template

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
