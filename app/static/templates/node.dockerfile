# Node — unoptimized single-stage image
FROM node:20
WORKDIR /usr/src/app
# Copy everything (no .dockerignore) which bloats the image and breaks caching
ADD . /usr/src/app
# Install deps in a separate layer (no production-only install)
RUN npm install
# Build step separated into its own layer
RUN npm run build
# Install extra OS packages in another layer
RUN apt-get update
RUN apt-get install -y build-essential git python3
RUN rm -rf /var/lib/apt/lists/*
EXPOSE 3000
CMD ["node", "index.js"]
