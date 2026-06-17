FROM node:20-alpine

WORKDIR /app

# Install a simple static file server
RUN npm install -g serve

# Copy static assets
COPY . .

# Expose port 8000
EXPOSE 8000

# Serve the current directory on port 8000
CMD ["serve", "-l", "8000", "."]
