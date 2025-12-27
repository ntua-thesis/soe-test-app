# Use a lightweight Python image
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Install system dependencies (Helm, kubectl, and curl)
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Helm
RUN curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 \
    && chmod 700 get_helm.sh \
    && ./get_helm.sh

# Install kubectl
# Using the stable release URL to ensure we get a compatible version
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/

# Copy requirements and install Python dependencies
# We keep this because requirements change rarely compared to script logic
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create the results directory structure
RUN mkdir -p /app/results

# Default command (can be overridden, but useful as a default)
CMD ["python", "-u", "experiment_runner.py"]
