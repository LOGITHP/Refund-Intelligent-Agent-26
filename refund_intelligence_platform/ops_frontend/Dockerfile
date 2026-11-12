FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
ARG VITE_AGENT_API_URL=http://localhost:8100
ENV VITE_AGENT_API_URL=$VITE_AGENT_API_URL
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
ENV PORT=3002 \
    NGINX_ENVSUBST_FILTER='^PORT$'
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 3002
CMD ["nginx", "-g", "daemon off;"]
