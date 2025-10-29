#!/bin/sh
# Student submission script
# This is a sample solution that should pass the AutoMark tests

echo "Hello from the student submission!"
echo "This script demonstrates a passing solution."

# Get the code directory (where this script is located)
CODE_DIR="${CODE_DIR:-/tmp/code}"

# Create the required output file
cat > "$CODE_DIR/output.txt" << EOF
Student Submission Output
========================
This file was created by the solution script.
Timestamp: $(date)
Status: Completed successfully
EOF

echo "Output file created at: $CODE_DIR/output.txt"

# Exit with success code
exit 0