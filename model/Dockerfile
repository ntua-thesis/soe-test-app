# Use a lightweight Python image
# We use 3.11-slim to keep the image size down while ensuring compatibility
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
# --no-cache-dir keeps the image smaller by removing pip cache
RUN pip install --no-cache-dir -r requirements.txt

# Create a directory for input/output files
RUN mkdir -p /app/results

