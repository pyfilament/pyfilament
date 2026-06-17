FROM node:23-alpine AS base
WORKDIR /app
COPY package.json ./
# no package-lock.json because rollup is locked to darwin rather than linux
RUN npm install
COPY . .
RUN npm run build
CMD ["npm", "run", "preview"]
