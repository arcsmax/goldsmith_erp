# frontend/Dockerfile
FROM node:18-alpine

# Corepack/Yarn aktivieren
RUN corepack enable \
  && corepack prepare yarn@stable --activate

WORKDIR /app

# Meta‑Dateien kopieren
COPY package.json yarn.lock ./

# Dependencies installieren
RUN yarn install --immutable

# Restliche App kopieren
COPY . .

EXPOSE 3000

CMD ["yarn", "dev", "--host", "0.0.0.0"]

