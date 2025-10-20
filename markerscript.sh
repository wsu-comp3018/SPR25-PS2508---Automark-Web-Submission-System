#!/bin/sh

# Simple hello world marker script for testing

echo "Hello World from AutoMark!"

# Set up environment
RESULT_DIR="${RESULT_DIR:-/tmp/results}"
CODE_DIR="${CODE_DIR:-/tmp/code}"
MARKER_DIR="${MARKER_DIR:-/tmp/marker}"

echo "Result directory: $RESULT_DIR"
echo "Code directory: $CODE_DIR"
echo "Marker directory: $MARKER_DIR"

# Create results directory
mkdir -p "$RESULT_DIR"

# Create a simple result
cat > "$RESULT_DIR/result.json" << "RESULT_EOF"
{
    "ok": true,
    "score": 100,
    "message": "Hello World test completed successfully!"
}
RESULT_EOF

echo "Marker script completed successfully!"
exit 0