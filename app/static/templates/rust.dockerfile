# Rust — unoptimized single-stage build
FROM rust:1.79
WORKDIR /usr/src/app
# Copy the whole context before building; this reduces dependency-layer cache reuse
COPY . .
# The compiler and build tools remain in the final image
RUN cargo build --release
EXPOSE 8080
# Replace `app` with the binary name from Cargo.toml
CMD ["./target/release/app"]
