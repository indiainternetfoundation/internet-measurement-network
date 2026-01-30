#!/bin/bash
# Complete Docker cleanup and fresh start script for IMN project

set -e  # Exit on any error

echo "========================================"
echo "Docker Complete Cleanup - IMN Project"
echo "========================================"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker daemon is not running. Please start Docker first."
    exit 1
fi

# Step 1: Stop all running containers from both compose files
echo "Step 1: Stopping all containers..."
if [ -f "core-pipeline.yml" ]; then
    docker-compose -f core-pipeline.yml down
fi
if [ -f "docker/docker-compose.yml" ]; then
    docker-compose -f docker/docker-compose.yml down
fi
echo "✓ Containers stopped"
echo ""

# Step 2: Remove all containers (including stopped ones)
echo "Step 2: Removing all containers..."
docker ps -a --filter "name=internet-measurement-network" --format "{{.ID}}" | xargs -r docker rm -f 2>/dev/null || true
docker ps -a --filter "name=server" --format "{{.ID}}" | xargs -r docker rm -f 2>/dev/null || true
docker ps -a --filter "name=agent" --format "{{.ID}}" | xargs -r docker rm -f 2>/dev/null || true
docker ps -a --filter "name=opensearch" --format "{{.ID}}" | xargs -r docker rm -f 2>/dev/null || true
docker ps -a --filter "name=otel-collector" --format "{{.ID}}" | xargs -r docker rm -f 2>/dev/null || true
docker ps -a --filter "name=data-prepper" --format "{{.ID}}" | xargs -r docker rm -f 2>/dev/null || true
# Remove any remaining containers with project-related names
docker ps -a --format "{{.Names}}	{{.ID}}" | grep -E "(server|agent|nats|postgres|clickhouse|opensearch|otel|imn)" | cut -f2 | xargs -r docker rm -f 2>/dev/null || true
echo "✓ Containers removed"
echo ""

# Step 3: Remove all images
echo "Step 3: Removing all images..."
docker images --filter "reference=internet-measurement-network*" --format "{{.ID}}" | xargs -r docker rmi -f 2>/dev/null || true
docker images --filter "reference=*server*" --format "{{.ID}}" | xargs -r docker rmi -f 2>/dev/null || true
docker images --filter "reference=*agent*" --format "{{.ID}}" | xargs -r docker rmi -f 2>/dev/null || true
docker images --filter "reference=*imn*" --format "{{.ID}}" | xargs -r docker rmi -f 2>/dev/null || true
# Remove dangling images
docker images -f "dangling=true" -q | xargs -r docker rmi -f 2>/dev/null || true
echo "✓ Images removed"
echo ""

# Step 4: Remove all volumes
echo "Step 4: Removing all volumes..."
docker volume ls --filter "name=internet-measurement-network" --format "{{.Name}}" | xargs -r docker volume rm -f 2>/dev/null || true
docker volume ls --filter "name=postgres_data" --format "{{.Name}}" | xargs -r docker volume rm -f 2>/dev/null || true
docker volume ls --filter "name=clickhouse_data" --format "{{.Name}}" | xargs -r docker volume rm -f 2>/dev/null || true
docker volume ls --filter "name=opensearch" --format "{{.Name}}" | xargs -r docker volume rm -f 2>/dev/null || true
docker volume prune -f
echo "✓ Volumes removed"
echo ""

# Step 5: Remove networks
echo "Step 5: Removing networks..."
docker network ls --filter "name=internet-measurement-network" --format "{{.Name}}" | xargs -r docker network rm 2>/dev/null || true
docker network ls --filter "name=aiori-net" --format "{{.Name}}" | xargs -r docker network rm 2>/dev/null || true
docker network ls --filter "name=default" --format "{{.Name}}" | xargs -r docker network rm 2>/dev/null || true
echo "✓ Networks removed"
echo ""

# Step 6: Clean up build cache
echo "Step 6: Cleaning build cache..."
docker builder prune -af
echo "✓ Build cache cleaned"
echo ""

# Step 7: Remove any orphaned resources
echo "Step 7: Removing orphaned resources..."
docker system prune -af --volumes
echo "✓ Orphaned resources removed"
echo ""

# Step 8: Clean up local files (optional - be careful!)
echo "Step 8: Cleaning local files..."
if [ "$1" = "--include-files" ]; then
    echo "⚠️  Removing local data files..."
    rm -rf server/db/data.db 2>/dev/null || true
    rm -rf .cache 2>/dev/null || true
    rm -rf __pycache__ 2>/dev/null || true
    find . -name "*.pyc" -delete 2>/dev/null || true
    find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    echo "✓ Local files cleaned"
else
    echo "ℹ️  Skipping local file cleanup (use --include-files to remove local data)"
fi
echo ""

# Step 9: Verify cleanup
echo "========================================"
echo "Cleanup Verification"
echo "========================================"
echo ""

echo "Remaining containers:"
REMAINING_CONTAINERS=$(docker ps -a --format "{{.Names}}" | grep -E "(server|agent|nats|postgres|clickhouse|opensearch|otel|imn|internet-measurement)" || true)
if [ -z "$REMAINING_CONTAINERS" ]; then
    echo "  None ✓"
else
    echo "  ❌ Remaining containers found:"
    echo "$REMAINING_CONTAINERS"
fi
echo ""

echo "Remaining images:"
REMAINING_IMAGES=$(docker images --format "{{.Repository}}" | grep -E "(internet-measurement|server|agent|imn)" || true)
if [ -z "$REMAINING_IMAGES" ]; then
    echo "  None ✓"
else
    echo "  ❌ Remaining images found:"
    echo "$REMAINING_IMAGES"
fi
echo ""

echo "Remaining volumes:"
REMAINING_VOLUMES=$(docker volume ls --format "{{.Name}}" | grep -E "(internet-measurement|postgres|clickhouse|opensearch)" || true)
if [ -z "$REMAINING_VOLUMES" ]; then
    echo "  None ✓"
else
    echo "  ❌ Remaining volumes found:"
    echo "$REMAINING_VOLUMES"
fi
echo ""

echo "Remaining networks:"
REMAINING_NETWORKS=$(docker network ls --format "{{.Name}}" | grep -E "(internet-measurement|aiori)" || true)
if [ -z "$REMAINING_NETWORKS" ]; then
    echo "  None ✓"
else
    echo "  ❌ Remaining networks found:"
    echo "$REMAINING_NETWORKS"
fi
echo ""

# Check if cleanup was successful
if [ -z "$REMAINING_CONTAINERS" ] && [ -z "$REMAINING_IMAGES" ] && [ -z "$REMAINING_VOLUMES" ] && [ -z "$REMAINING_NETWORKS" ]; then
    echo "✅ Cleanup completed successfully!"
else
    echo "⚠️  Cleanup completed with some resources remaining"
fi

echo ""
echo "========================================"
echo "Cleanup Complete!"
echo "========================================"
echo ""

echo "Next steps:"
echo "1. Run: docker-compose -f core-pipeline.yml build --no-cache"
echo "2. Run: docker-compose -f core-pipeline.yml up -d"
echo ""
echo "Optional: To include local file cleanup, run:"
echo "  ./tests/cleanup.sh --include-files"
echo ""

# Exit with appropriate code
if [ -z "$REMAINING_CONTAINERS" ] && [ -z "$REMAINING_IMAGES" ] && [ -z "$REMAINING_VOLUMES" ] && [ -z "$REMAINING_NETWORKS" ]; then
    exit 0
else
    exit 1
fi