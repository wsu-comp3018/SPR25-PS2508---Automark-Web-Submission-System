#!/bin/bash
# Demo Marker Script - Grades based on output patterns
# This script runs student code and assigns grades based on what it prints

set -e

echo "=== AutoMark Demo Grader ==="
echo "Marker Directory: $MARKER_DIR"
echo "Code Directory: $CODE_DIR"
echo "Result Directory: $RESULT_DIR"
echo ""

# Find the student's Python file (usually solution.py)
STUDENT_FILE="$CODE_DIR/solution.py"

if [ ! -f "$STUDENT_FILE" ]; then
    echo "ERROR: solution.py not found in submission"
    cat > "$RESULT_DIR/result.json" <<EOF
{
  "score": 0,
  "feedback": "Error: solution.py not found in submission. Please submit a file named 'solution.py'.",
  "passed": false
}
EOF
    exit 0
fi

echo "Found student file: $STUDENT_FILE"
echo "Executing student code..."
echo ""1

# Execute student code and capture output
OUTPUT=$(cd "$CODE_DIR" && python3 solution.py 2>&1) || {
    echo "ERROR: Code execution failed"
    cat > "$RESULT_DIR/result.json" <<EOF
{
  "score": 0,
  "feedback": "Error: Code execution failed. Check your syntax and logic.\n\nError output:\n$OUTPUT",
  "passed": false
}
EOF
    exit 0
}

echo "Student output:"
echo "$OUTPUT"
echo ""

# Grade based on output patterns
SCORE=0
FEEDBACK=""
PASSED=false

if echo "$OUTPUT" | grep -q "Full Grade Example"; then
    SCORE=100
    FEEDBACK="Excellent work! Your solution produces the correct output: 'Full Grade Example'. All requirements met."
    PASSED=true
elif echo "$OUTPUT" | grep -q "High Grade Example"; then
    SCORE=85
    FEEDBACK="Great job! Your solution produces 'High Grade Example'. Minor improvement possible."
    PASSED=true
elif echo "$OUTPUT" | grep -q "Good Grade Example"; then
    SCORE=70
    FEEDBACK="Good work! Your solution produces 'Good Grade Example'. Some requirements met."
    PASSED=true
elif echo "$OUTPUT" | grep -q "Partial Grade Example"; then
    SCORE=50
    FEEDBACK="Partial credit. Your solution produces 'Partial Grade Example'. Needs significant improvement."
    PASSED=false
elif echo "$OUTPUT" | grep -q "Basic Grade Example"; then
    SCORE=30
    FEEDBACK="Basic attempt. Your solution produces 'Basic Grade Example'. Most requirements not met."
    PASSED=false
else
    SCORE=10
    FEEDBACK="Minimal effort. Output does not match any expected pattern. Please review the assignment requirements.\n\nYour output was:\n$OUTPUT"
    PASSED=false
fi

echo "Grading complete!"
echo "Score: $SCORE"
echo "Passed: $PASSED"
echo ""

# Write result.json
cat > "$RESULT_DIR/result.json" <<EOF
{
  "score": $SCORE,
  "feedback": "$FEEDBACK",
  "passed": $PASSED,
  "output": $(echo "$OUTPUT" | jq -Rs .)
}
EOF

echo "Result written to $RESULT_DIR/result.json"
exit 0
