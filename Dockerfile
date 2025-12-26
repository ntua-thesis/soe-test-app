# --- Stage 1: Builder ---
# We use the official Go image to compile the code
FROM golang:1.21-alpine AS builder

# Set the working directory inside the container
WORKDIR /app

# Copy the source code into the container
# (Assuming your code is in a file named main.go)
COPY main.go .

# Initialize a go module (required for modern Go, even for single files)
RUN go mod init prime-generator

# Build the application
# CGO_ENABLED=0: Disables C bindings (makes it a static binary)
# -o server: Names the output binary "server"
# -ldflags="-s -w": Strips debug info to reduce binary size
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o server main.go

# --- Stage 2: Runner ---
# We use a "distroless" static image. 
# It has no shell, no package manager, just what's needed to run the binary.
FROM gcr.io/distroless/static-debian12

# Set the working directory
WORKDIR /

# Copy the binary from the builder stage
COPY --from=builder /app/server /server

# Expose the port defined in your Go code
EXPOSE 8080

# Command to run when the container starts
CMD ["/server"]
