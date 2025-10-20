#!/bin/bash
# Wrapper script for the Python post-commit hook

# Log that the wrapper was called
echo "Wrapper called with args: $@" >> /tmp/wrapper-debug.log

# Call the Python hook
/usr/bin/python3 /var/svn/hooks/post-commit-live.py "$@"
exit_code=$?

# Log the result
echo "Python hook exited with code: $exit_code" >> /tmp/wrapper-debug.log

exit $exit_code
