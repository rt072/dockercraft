# Go — unoptimized single-stage build on Ubuntu
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y golang-go git build-essential
WORKDIR /go/src/app
COPY . .
RUN go mod download
RUN go build -o app .
EXPOSE 8080
CMD ["/go/src/app/app"]
