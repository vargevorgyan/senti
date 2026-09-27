FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# The Mac installer and the Senti engine, served by this server so every Mac gets the version that matches it
# (engine = the ../engine folder, passed as an extra build context in docker-compose.yml)
FROM alpine:3.22 AS engine-bundle
COPY --from=engine pyproject.toml uv.lock README.md /bundle/
COPY --from=engine src /bundle/src
COPY --from=engine hook /bundle/hook
COPY --from=engine install.sh /install.sh
RUN find /bundle -name __pycache__ -prune -exec rm -rf {} + \
 && tar czf /senti-engine.tar.gz -C /bundle . \
 && cd / && sha256sum senti-engine.tar.gz > senti-engine.tar.gz.sha256

FROM nginx:1.29-alpine
RUN apk add --no-cache openssl
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY nginx/security-headers.conf /etc/nginx/snippets/senti-security-headers.conf
COPY nginx/proxy.conf /etc/nginx/snippets/senti-proxy.conf
COPY tls-cert.sh /docker-entrypoint.d/10-senti-tls-cert.sh
RUN chmod +x /docker-entrypoint.d/10-senti-tls-cert.sh
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=engine-bundle /senti-engine.tar.gz /senti-engine.tar.gz.sha256 /usr/share/nginx/html/downloads/
COPY --from=engine-bundle /install.sh /usr/share/nginx/html/install.sh
EXPOSE 80 443
