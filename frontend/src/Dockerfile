FROM node:18-alpine

WORKDIR /app

# Dependencies installieren
COPY package.json package-lock.json* ./
RUN npm ci

# App-Code kopieren
COPY . .

# Port exponieren
EXPOSE 3000

# Entwicklungsserver starten
CMD ["npm", "run", "dev", "--", "--host"]