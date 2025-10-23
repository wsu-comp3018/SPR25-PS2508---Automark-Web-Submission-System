"""
contribution.py

This script calculates each contributor's code contribution in a Git repository.

Methodology:
1. It scans all git-tracked files with specific extensions (e.g., .py, .js, .java).
2. For each file, it runs `git blame --line-porcelain` to see which author last modified each line.
3. It counts the number of lines attributed to each author.
4. It sums these counts across all files to get the total unique lines per contributor.
5. It calculates the percentage of total lines each contributor owns.

Notes:
- Lines that were added but later removed by someone else are not counted.
- Only files with extensions listed in the EXTENSIONS list are included.
- On Windows, it handles potential Unicode decoding issues from git output.
"""

import os
import subprocess
from collections import defaultdict

# File extensions to include
EXTENSIONS = ['.py', '.js', '.java', '.sh', '.css', '.html']  # add more as needed

def get_git_tracked_files():
    """Get all git-tracked files in the repo."""
    result = subprocess.run(
        ['git', 'ls-files'],
        capture_output=True,
        text=True,
        encoding='utf-8',   # force UTF-8
        errors='ignore'     # ignore undecodable chars
    )
    files = result.stdout.splitlines()
    return [f for f in files if os.path.splitext(f)[1] in EXTENSIONS]

def get_line_contributors(file_path):
    """Return a dict of {author: number_of_lines} for a file."""
    result = subprocess.run(
        ['git', 'blame', '--line-porcelain', file_path],
        capture_output=True,
        text=True,
        encoding='utf-8',   # force UTF-8
        errors='ignore'     # ignore undecodable chars
    )
    if result.stdout is None:
        return defaultdict(int)

    lines = result.stdout.splitlines()
    contrib_count = defaultdict(int)
    for line in lines:
        if line.startswith('author '):
            author = line[7:].strip()
            contrib_count[author] += 1
    return contrib_count

def main():
    total_contrib = defaultdict(int)
    files = get_git_tracked_files()
    if not files:
        print("No tracked files with the specified extensions found.")
        return

    for f in files:
        file_contrib = get_line_contributors(f)
        for author, count in file_contrib.items():
            total_contrib[author] += count

    total_lines = sum(total_contrib.values())
    if total_lines == 0:
        print("No contributions found.")
        return

    print(f"{'Contributor':<25} | {'Lines':<10} | {'% of Total':<10}")
    print("-" * 50)
    for author, count in sorted(total_contrib.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total_lines) * 100
        print(f"{author:<25} | {count:<10} | {percentage:>7.2f}%")

if __name__ == "__main__":
    main()