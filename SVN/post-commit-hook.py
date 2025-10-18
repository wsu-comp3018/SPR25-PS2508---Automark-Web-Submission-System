#!/usr/bin/python3
"""
SVN Post-commit hook for AutoMark submission collection

This script runs after each SVN commit and:
1. Extracts the commit information (author, revision, files)
2. Parses the repository path to determine assignment and student
3. Calls the AutoMark API to trigger grading
"""

import sys
import os
import subprocess
import json
import re
import sqlite3
from datetime import datetime

def run_command(cmd_list):
    """Run a shell command and return output"""
    try:
        result = subprocess.run(cmd_list, capture_output=True, text=True)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except Exception as e:
        return "", str(e), 1

def extract_commit_info(repo_path, revision):
    """Extract commit information from SVN"""
    # Get commit author
    cmd = ['svnlook', 'author', repo_path, '-r', str(revision)]
    stdout, stderr, returncode = run_command(cmd)
    
    if returncode != 0:
        print(f"Error getting commit author: {stderr}")
        return None
    
    author = stdout.strip()
    
    # Get commit message
    cmd = ['svnlook', 'log', repo_path, '-r', str(revision)]
    stdout, stderr, returncode = run_command(cmd)
    message = stdout.strip() if returncode == 0 else ""
    
    return {
        'revision': revision,
        'author': author,
        'message': message
    }

def parse_svn_path(repo_path, revision):
    """Parse SVN repository path to extract assignment information"""
    # Get changed paths in this revision
    cmd = ['svnlook', 'changed', repo_path, '-r', str(revision)]
    stdout, stderr, returncode = run_command(cmd)
    
    if returncode != 0:
        print(f"Error getting changed paths: {stderr}")
        return None
    
    # Look for student repository paths
    # Format: "U   student-repos/2025-AUT-COMP_0067-Assignment1/student_david/main.py"
    student_repo_pattern = r'student-repos/(\d{4}-(AUT|SPR)-([A-Z0-9_]+)-Assignment(\d+))/([^/]+)'
    
    for line in stdout.split('\n'):
        if 'student-repos/' in line:
            match = re.search(student_repo_pattern, line)
            if match:
                year_sem_subject_assignment = match.group(1)  # 2025-AUT-COMP_0067-Assignment1
                semester = match.group(2)  # AUT
                subject_code = match.group(3)  # COMP_0067
                assignment_number = int(match.group(4))  # 1
                student_username = match.group(5)  # student_david
                
                return {
                    'year_sem_subject_assignment': year_sem_subject_assignment,
                    'year': year_sem_subject_assignment.split('-')[0],
                    'semester': semester,
                    'subject_code': subject_code,
                    'assignment_number': assignment_number,
                    'student_username': student_username,
                    'svn_path': f"student-repos/{year_sem_subject_assignment}/{student_username}"
                }
    
    return None

def get_folder_id_from_assignment(subject_code, assignment_number, year, semester):
    """Query the database to find the folder_id for this assignment"""
    try:
        # Connect to the database (mounted volume in docker-compose)
        db_path = "/app/data/automark.db"
        if not os.path.exists(db_path):
            print(f"Database not found at {db_path}")
            return None
        
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Query for the folder that matches this assignment
        c.execute("""
            SELECT f.id, f.name, f.subject_code, f.assignment_number
            FROM folders f
            WHERE f.subject_code = ? AND f.assignment_number = ?
            ORDER BY f.created_at DESC
            LIMIT 1
        """, (subject_code, assignment_number))
        
        row = c.fetchone()
        conn.close()
        
        if row:
            folder_id = row['id']
            print(f"Found folder_id {folder_id} for {subject_code} Assignment{assignment_number}")
            return folder_id
        else:
            print(f"Warning: Could not find folder_id for {subject_code} Assignment{assignment_number}")
            return None
        
    except Exception as e:
        print(f"Error querying database for folder_id: {e}")
        return None

def notify_automark_api(assignment_info, commit_info):
    """Notify the AutoMark API of a new submission"""
    try:
        # Get folder_id from assignment info
        folder_id = get_folder_id_from_assignment(
            assignment_info['subject_code'],
            assignment_info['assignment_number'],
            assignment_info['year'],
            assignment_info['semester']
        )
        
        if not folder_id:
            print(f"❌ Could not determine folder_id for assignment")
            return False
        
        # Prepare the API call
        api_url = "http://automark-api:8000/api/v1/submissions/receive_svn"
        
        payload = {
            "folder_id": folder_id,
            "student_username": assignment_info['student_username'],
            "svn_url": f"svn://automark-svn/automark/{assignment_info['svn_path']}",
            "revision": commit_info['revision']
        }
        
        print(f"📡 Calling API: {api_url}")
        print(f"📦 Payload: {json.dumps(payload, indent=2)}")
        
        # Use curl instead of requests to avoid import issues
        curl_cmd = [
            'curl', '-X', 'POST', api_url,
            '-H', 'Content-Type: application/json',
            '-d', json.dumps(payload),
            '--connect-timeout', '10',
            '--max-time', '30'
        ]
        
        stdout, stderr, returncode = run_command(curl_cmd)
        
        if returncode == 0:
            print(f"✅ API call successful: {stdout}")
            return True
        else:
            print(f"❌ API call failed: {stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error calling AutoMark API: {e}")
        return False

def main():
    """Main post-commit hook function"""
    # Debug: Write to a file to see if hook is being called
    try:
        with open('/tmp/hook-debug.log', 'a') as f:
            f.write(f"Hook called with args: {sys.argv}\n")
            f.write(f"Python path: {sys.executable}\n")
            f.write(f"Working directory: {os.getcwd()}\n")
    except Exception as e:
        try:
            with open('/tmp/hook-error.log', 'a') as f:
                f.write(f"Debug write failed: {e}\n")
        except:
            pass
    
    try:
        if len(sys.argv) < 3:
            print("Usage: post-commit-hook.py <repo-path> <revision> [transaction]")
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
        
        # Parse the SVN path to determine assignment
        assignment_info = parse_svn_path(repo_path, revision)
        if not assignment_info:
            print("❌ Could not parse assignment information from SVN path")
            print("ℹ️  This might not be a student submission commit")
            sys.exit(0)  # Not an error, just not a student submission
        
        print(f"📚 Assignment: {assignment_info['subject_code']} Assignment{assignment_info['assignment_number']}")
        print(f"👨‍🎓 Student: {assignment_info['student_username']}")
        print(f"📅 Year/Semester: {assignment_info['year']} {assignment_info['semester']}")
        
        # Notify the AutoMark API
        success = notify_automark_api(assignment_info, commit_info)
        
        if success:
            print("✅ Post-commit hook completed successfully")
            sys.exit(0)
        else:
            print("❌ Post-commit hook failed")
            sys.exit(1)
    
    except Exception as e:
        # Log the error to a file
        try:
            with open('/tmp/hook-error.log', 'a') as f:
                f.write(f"Hook error: {e}\n")
                f.write(f"Args: {sys.argv}\n")
                import traceback
                f.write(f"Traceback: {traceback.format_exc()}\n")
        except:
            pass
        print(f"❌ Hook failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
