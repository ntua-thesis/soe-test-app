#!/bin/bash

# Configuration
NEXUS_URL="${NEXUS_URL:-https://nexus.lefto.org}"
REPOSITORY="${NEXUS_REPOSITORY:-ahp-autoscaler}"
VERSION="${ARTIFACT_VERSION:-0.1.2}"
ARTIFACTS_DIR="${ARTIFACTS_DIR:-./results}"

# Prompt for credentials if not set
if [[ -z "$NEXUS_USERNAME" ]]; then
    read -p "Nexus Username: " NEXUS_USERNAME
fi

if [[ -z "$NEXUS_PASSWORD" ]]; then
    read -s -p "Nexus Password: " NEXUS_PASSWORD
    echo  # New line after password input
fi

# Validate inputs
if [[ -z "$NEXUS_USERNAME" || -z "$NEXUS_PASSWORD" ]]; then
    echo "Error: Username and password are required"
    exit 1
fi

if [[ ! -d "$ARTIFACTS_DIR" ]]; then
    echo "Error: Artifacts directory '$ARTIFACTS_DIR' not found"
    exit 1
fi

echo "Configuration:"
echo "  Nexus URL: $NEXUS_URL"
echo "  Repository: $REPOSITORY"
echo "  Version: $VERSION"
echo "  Artifacts Dir: $ARTIFACTS_DIR"
echo "  Username: $NEXUS_USERNAME"
echo ""

# Upload function
upload_file() {
    local file="$1"
    local filename=$(basename "$file")
    local name="${filename%.*}"
    local extension="${filename##*.}"
    local versioned_name="${name}-${VERSION}.${extension}"
    
    echo "Uploading $filename as $versioned_name..."
    
    curl -k \
        -u "${NEXUS_USERNAME}:${NEXUS_PASSWORD}" \
        -X PUT \
        "${NEXUS_URL}/repository/${REPOSITORY}/${versioned_name}" \
        -T "$file" \
        --progress-bar
    
    if [ $? -eq 0 ]; then
        echo "✓ Successfully uploaded $versioned_name"
    else
        echo "✗ Failed to upload $versioned_name"
        return 1
    fi
}

# Count files first
file_count=$(find "$ARTIFACTS_DIR" -maxdepth 1 -type f | wc -l)
echo "Found $file_count files to upload"

if [ $file_count -eq 0 ]; then
    echo "No files found in $ARTIFACTS_DIR"
    exit 0
fi

# Confirm before proceeding
read -p "Proceed with upload? (y/N): " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Upload cancelled"
    exit 0
fi

echo ""

# Upload all files in directory
success_count=0
for file in "$ARTIFACTS_DIR"/*; do
    if [ -f "$file" ]; then
        if upload_file "$file"; then
            ((success_count++))
        fi
        echo ""
    fi
done

echo "Upload complete: $success_count/$file_count files uploaded successfully"
