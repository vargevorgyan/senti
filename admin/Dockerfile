FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.29-alpine
RUN apk add --no-cache openssl
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY tls-cert.sh /docker-entrypoint.d/10-senti-tls-cert.sh
RUN chmod +x /docker-entrypoint.d/10-senti-tls-cert.sh
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80 443
