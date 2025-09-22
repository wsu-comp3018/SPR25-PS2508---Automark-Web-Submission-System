#!/usr/bin/env python3
"""
SVN Post-commit hook for AutoMark submission collection

This script runs after each SVN commit and:
1. Extracts the commit information (author, revision, files)
2. Copies the committed files to the submissions collection area
3. Notifies the AutoMark API of the new submission
"""

import sys
import os
import subprocess
import json
import shutil
from datetime import datetime
from pathlib import Path

def run_command(cmd):
    """Run a shell command and return output"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except Exception as e:
        return "", str(e), 1

def extract_commit_info(repo_path, revision):
    """Extract commit information from SVN"""
    cmd = f'svn log -r {revision} --xml "{repo_path}"'
    stdout, stderr, returncode = run_command(cmd)
    
    if returncode != 0:
        print(f"Error getting commit info: {stderr}")
        return None
    
    # Parse commit info (simplified - in production use proper XML parsing)
    lines = stdout.split('\n')
    author = None
    date = None
    message = None
    
    for line in lines:
        if 'author=' in line:
            author = line.split('author="')[1].split('"')[0] if 'author="' in line else None
        elif 'date=' in line:
            date = line.split('date="')[1].split('"')[0] if 'date="' in line else None
        elif '<msg>' in line and '</msg>' in line:
            message = line.replace('<msg>', '').replace('</msg>', '').strip()
    
    return {
        'revision': revision,
        'author': author,
        'date': date,
        'message': message
    }

def get_changed_files(repo_path, revision):
    """Get list of files changed in this revision"""
    cmd = f'svn diff -r {int(revision)-1}:{revision} --summarize "{repo_path}"'
    stdout, stderr, returncode = run_command(cmd)
    
    if returncode != 0:
        return []
    
    files = []
    for line in stdout.split('\n'):
        if line.strip():
            # Format: "M    /path/to/file" or "A    /path/to/file"
            parts = line.split()
            if len(parts) >= 2:
                files.append(parts[1])
    
    return files

def export_revision(repo_path, revision, export_path):
    """Export a specific revision to a directory"""
    cmd = f'svn export -r {revision} "{repo_path}" "{export_path}" --force'
    stdout, stderr, returncode = run_command(cmd)
    return returncode == 0

def collect_submission(repo_path, revision, commit_info):
    """Collect the submission files and organize them"""
    
    # Parse the repository path to understand what was submitted
    # Expected path format: student working copy in SSH container
    # We need to determine: student, subject, assignment
    
    author = commit_info['author']
    timestamp = datetime.now().isoformat()
    
    # For now, assume this is a student submission
    # In a full implementation, we'd parse the path to determine the assignment
    
    print(f"📝 Processing submission from {author}, revision {revision}")
    
    # Create submission directory structure
    submissions_base = "/var/submissions"
    submission_dir = f"{submissions_base}/temp/{author}/r{revision}_{timestamp}"
    
    try:
        os.makedirs(submission_dir, exist_ok=True)
        
        # Export the revision
        if export_revision(repo_path, revision, submission_dir):
            print(f"✅ Exported revision {revision} to {submission_dir}")
            
            # Create metadata file
            metadata = {
                'revision': revision,
                'author': author,
                'timestamp': timestamp,
                'commit_message': commit_info['message'],
                'commit_date': commit_info['date']
            }
            
            with open(f"{submission_dir}/submission_metadata.json", 'w') as f:
                json.dump(metadata, f, indent=2)
            
            print(f"✅ Submission collected for {author}")
            
            # TODO: Notify AutoMark API of new submission
            # notify_automark_api(metadata)
            
        else:
            print(f"❌ Failed to export revision {revision}")
            
    except Exception as e:
        print(f"❌ Error collecting submission: {e}")

def notify_automark_api(submission_metadata):
    """Notify the AutoMark API of a new submission"""
    # TODO: Make HTTP request to API endpoint
    # This would include:
    # - Student ID
    # - Assignment ID  
    # - Submission path
    # - Commit metadata
    pass

def main():
    """Main post-commit hook function"""
    if len(sys.argv) != 3:
        print("Usage: post-commit-hook.py <repo-path> <revision>")
        sys.exit(1)
    
    repo_path = sys.argv[1]
    revision = sys.argv[2]
    
    print(f"🔄 SVN Post-commit hook triggered")
    print(f"📁 Repository: {repo_path}")
    print(f"📄 Revision: {revision}")
    
    # Extract commit information
    commit_info = extract_commit_info(repo_path, revision)
    if not commit_info:
        print("❌ Failed to extract commit information")
        sys.exit(1)
    
    print(f"👤 Author: {commit_info['author']}")
    print(f"💬 Message: {commit_info['message']}")
    
    # Collect the submission
    collect_submission(repo_path, revision, commit_info)
    
    print("✅ Post-commit hook completed")

if __name__ == "__main__":
    main()
