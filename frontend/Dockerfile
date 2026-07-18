FROM node:22.14.0-alpine AS build

WORKDIR /src

COPY . .

# Validate expected static frontend assets exist.
RUN test -f index.html && test -f script.js && test -f style.css


FROM nginx:1.27.5-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
