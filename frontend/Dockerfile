# Purpose:
# - Build and package the frontend application for containerized execution.
#
# Current responsibilities:
# - Install Node dependencies
# - Build the Vite application
# - Serve the built static files through NGINX
#
# Notes:
# - Version pins are supplied through Docker build args from deploy/.env.
# - Keep the image small and predictable.
# - Separate dependency installation from source copy when possible for caching.

ARG NODE_VERSION=24.14.0
ARG NGINX_VERSION=1.27-alpine

FROM node:${NODE_VERSION}-alpine AS build

ARG NPM_VERSION=11.9.0

WORKDIR /app

RUN npm install -g npm@${NPM_VERSION}

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:${NGINX_VERSION} AS runtime

RUN apk add --no-cache openssl
ENV NGINX_EXTERNAL_HTTPS_PORT=443

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx/default.conf /etc/nginx/templates/default.conf.template
COPY nginx/40-generate-dev-cert.sh /docker-entrypoint.d/40-generate-dev-cert.sh
RUN chmod +x /docker-entrypoint.d/40-generate-dev-cert.sh

EXPOSE 80
EXPOSE 443

CMD ["nginx", "-g", "daemon off;"]
