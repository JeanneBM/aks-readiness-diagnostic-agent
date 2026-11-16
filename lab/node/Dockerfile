FROM node:22-alpine
WORKDIR /app
COPY server.js .
USER 10001:10001
ENV NODE_ENV=production
CMD ["node", "server.js"]
