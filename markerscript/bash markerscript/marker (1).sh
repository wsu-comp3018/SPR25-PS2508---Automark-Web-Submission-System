#!/bin/sh
set -e  # Exit on any error

# Enhanced marker script for AutoMark testing
# This script tests a student's solution against expected outputs

echo "=== AutoMark Test Execution ==="
echo "Starting marker script..."

# Set up environment with defaults
RESULT_DIR="${RESULT_DIR:-/tmp/results}"
CODE_DIR="${CODE_DIR:-/tmp/code}"
MARKER_DIR="${MARKER_DIR:-/tmp/marker}"

echo "Result directory: $RESULT_DIR"
echo "Code directory: $CODE_DIR"
echo "Marker directory: $MARKER_DIR"

# Create results directory
mkdir -p "$RESULT_DIR"

# Initialize score and test results
TOTAL_SCORE=0
MAX_SCORE=100
TESTS_PASSED=0
TESTS_FAILED=0
TEST_OUTPUT=""

# Function to add test result
add_test() {
    TEST_NAME="$1"
    TEST_PASSED="$2"
    TEST_MESSAGE="$3"
    POINTS="$4"
    
    if [ "$TEST_PASSED" = "true" ]; then
        TOTAL_SCORE=$((TOTAL_SCORE + POINTS))
        TESTS_PASSED=$((TESTS_PASSED + 1))
        STATUS="✓ PASS"
    else
        TESTS_FAILED=$((TESTS_FAILED + 1))
        STATUS="✗ FAIL"
    fi
    
    echo "  $STATUS - $TEST_NAME ($POINTS pts): $TEST_MESSAGE"
    TEST_OUTPUT="${TEST_OUTPUT}    {\"name\": \"$TEST_NAME\", \"passed\": $TEST_PASSED, \"message\": \"$TEST_MESSAGE\", \"points\": $POINTS},"
}

# Check if student script exists
echo ""
echo "Checking submission..."
if [ ! -f "$CODE_DIR/solution.sh" ]; then
    echo "ERROR: solution.sh not found in $CODE_DIR"
    cat > "$RESULT_DIR/result.json" << EOF
{
    "ok": false,
    "score": 0,
    "max_score": $MAX_SCORE,
    "message": "Submission not found: solution.sh is missing",
    "tests_passed": 0,
    "tests_failed": 1,
    "details": []
}
EOF
    exit 1
fi

# Make student script executable
chmod +x "$CODE_DIR/solution.sh"

echo "Running tests..."
echo ""

# Test 1: Script executes without errors (20 points)
echo "Test 1: Script execution"
if OUTPUT=$("$CODE_DIR/solution.sh" 2>&1); then
    add_test "Script Execution" "true" "Script ran successfully" 20
else
    add_test "Script Execution" "false" "Script failed to execute" 20
fi

# Test 2: Output contains expected greeting (30 points)
echo "Test 2: Output validation"
if echo "$OUTPUT" | grep -q "Hello"; then
    add_test "Output Contains Greeting" "true" "Found expected greeting" 30
else
    add_test "Output Contains Greeting" "false" "Greeting not found in output" 30
fi

# Test 3: Exit code is correct (20 points)
echo "Test 3: Exit code"
"$CODE_DIR/solution.sh" > /dev/null 2>&1
EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    add_test "Exit Code" "true" "Correct exit code (0)" 20
else
    add_test "Exit Code" "false" "Incorrect exit code ($EXIT_CODE)" 20
fi

# Test 4: Script creates required output file (30 points)
echo "Test 4: File creation"
"$CODE_DIR/solution.sh" > /dev/null 2>&1
if [ -f "$CODE_DIR/output.txt" ]; then
    add_test "File Creation" "true" "Required output file created" 30
else
    add_test "File Creation" "false" "Output file not created" 30
fi

# Remove trailing comma from TEST_OUTPUT
TEST_OUTPUT=$(echo "$TEST_OUTPUT" | sed 's/,$//')

# Calculate pass/fail status
if [ $TOTAL_SCORE -ge 70 ]; then
    OK_STATUS="true"
    OVERALL_MESSAGE="All tests passed! Great work!"
elif [ $TOTAL_SCORE -ge 50 ]; then
    OK_STATUS="true"
    OVERALL_MESSAGE="Most tests passed. Good effort!"
else
    OK_STATUS="false"
    OVERALL_MESSAGE="Several tests failed. Please review requirements."
fi

# Create final result JSON
cat > "$RESULT_DIR/result.json" << EOF
{
    "ok": $OK_STATUS,
    "score": $TOTAL_SCORE,
    "max_score": $MAX_SCORE,
    "message": "$OVERALL_MESSAGE",
    "tests_passed": $TESTS_PASSED,
    "tests_failed": $TESTS_FAILED,
    "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
    "details": [
$TEST_OUTPUT
    ]
}
EOF

echo ""
echo "=== Test Results ==="
echo "Score: $TOTAL_SCORE / $MAX_SCORE"
echo "Tests Passed: $TESTS_PASSED"
echo "Tests Failed: $TESTS_FAILED"
echo ""
echo "Results written to: $RESULT_DIR/result.json"
echo "Marker script completed!"

exit 0