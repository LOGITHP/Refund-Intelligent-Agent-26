FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
ARG VITE_API_URL=http://localhost:8000
ARG VITE_AGENT_API_URL=http://localhost:8100
ARG VITE_OPS_CONSOLE_URL=http://localhost:3002
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_AGENT_API_URL=$VITE_AGENT_API_URL
ENV VITE_OPS_CONSOLE_URL=$VITE_OPS_CONSOLE_URL
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
ENV PORT=3001 \
    NGINX_ENVSUBST_FILTER='^PORT$'
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 3001
CMD ["nginx", "-g", "daemon off;"]

