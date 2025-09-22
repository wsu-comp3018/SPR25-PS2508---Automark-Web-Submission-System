#!/usr/bin/env python3
"""
SSH User Management (Docker SDK)
- Matches main.py expectations:
  * create_ssh_user_for_registration(username, password) -> dict
  * class SSHUserManager with list_users() / delete_user(username)
- Talks to the 'automark-ssh' container via the host Docker socket.
"""

import os
import logging
from typing import Dict, Any

try:
    import docker  # pip: docker>=7,<8
except Exception as e:  # Keep import-time error visible in logs
    docker = None

logger = logging.getLogger(__name__)

_SSH_CONTAINER_NAME = os.getenv("SSH_CONTAINER_NAME", "automark-ssh")


class SSHUserManager:
    def __init__(self, container_name: str = None):
        self.container_name = container_name or _SSH_CONTAINER_NAME
        if docker is None:
            raise RuntimeError("Python Docker SDK not available. Ensure 'docker' is in requirements.")
        self.client = docker.from_env()

    def _container(self):
        try:
            return self.client.containers.get(self.container_name)
        except Exception as e:
            raise RuntimeError(f"SSH container '{self.container_name}' not found: {e}")

    def _exec_sh(self, sh_cmd: str) -> tuple[int, str]:
        """
        Run a shell command inside the SSH container and return (exit_code, output_text).
        Uses /bin/bash -lc to allow pipes and globs.
        """
        c = self._container()
        res = c.exec_run(["bash", "-lc", sh_cmd])
        # docker SDK v7 returns ExecResult with .exit_code and .output
        if hasattr(res, "exit_code"):
            code, out = res.exit_code, res.output
        else:  # fallback for tuple style
            code, out = res
        text = out.decode(errors="ignore") if isinstance(out, (bytes, bytearray)) else str(out)
        return int(code), text

    # ---------- helpers ----------
    def user_exists(self, username: str) -> bool:
        code, _ = self._exec_sh(f"id -u {username} >/dev/null 2>&1 || exit 1")
        return code == 0

    # ---------- public API expected by main.py ----------
    def create_user(self, username: str, password: str) -> Dict[str, Any]:
        result = {"success": False, "username": username, "message": "", "error": None}

        try:
            if self.user_exists(username):
                result["success"] = True
                result["message"] = f"User '{username}' already exists"
                return result

            # create user with home and bash shell
            code, out = self._exec_sh(f"useradd -m -s /bin/bash {username}")
            if code != 0:
                result["error"] = f"Failed to create user: {out}"
                return result

            # set password
            code, out = self._exec_sh(f"echo '{username}:{password}' | chpasswd")
            if code != 0:
                result["error"] = f"Failed to set password: {out}"
                return result

            # create simple assignment folders and set perms
            code, out = self._exec_sh(
                f"""
                set -e
                mkdir -p "/home/{username}/2025/AUT/PX/Assignment1" \
                         "/home/{username}/2025/AUT/PX/Assignment2" \
                         "/home/{username}/2025/SPR/PX/Assignment1" \
                         "/home/{username}/2025/SPR/PX/Assignment2"
                chown -R "{username}:{username}" "/home/{username}/2025"
                chmod 755 "/home/{username}/2025"
                chmod -R 755 "/home/{username}/2025"
                chmod 775 "/home/{username}/2025/AUT/PX/Assignment1" "/home/{username}/2025/AUT/PX/Assignment2" \
                          "/home/{username}/2025/SPR/PX/Assignment1" "/home/{username}/2025/SPR/PX/Assignment2"
                echo 'echo "Welcome to Automark, {username}! Your assignment folders are in ~/2025/"' >> "/home/{username}/.bashrc"

            # Create base directory structure (assignments will be created based on enrollments)
            success, stdout, stderr = self._exec_in_container([
                "bash", "-c", f"""
                # Create base year directory structure
                mkdir -p "/home/{username}/2025/AUT" \\
                         "/home/{username}/2025/SPR"
                
                # Set proper ownership and permissions
                chown -R "{username}:{username}" "/home/{username}/2025"
                chmod 755 "/home/{username}/2025"
                chmod -R 755 "/home/{username}/2025"
                """
            ])
            
            if not success:
                result["error"] = f"Failed to create chroot directories: {stderr}"
                return result
            
            # Create enrollment-based directories and welcome message
            success, stdout, stderr = self._exec_in_container([
                "bash", "-c", f"""
                # Create a welcome message with enrollment instructions
                echo 'echo "Welcome to Automark, {username}!"' >> "/home/{username}/.bashrc"
                echo 'echo "Your assignment folders are in ~/2025/"' >> "/home/{username}/.bashrc"
                echo 'echo "Use the web interface to enroll in subjects and get assignments."' >> "/home/{username}/.bashrc"
                chown "{username}:{username}" "/home/{username}/.bashrc"
                """
            )
            if code != 0:
                result["error"] = f"Failed to set up user environment: {out}"
                return result
            
            # Add user to SVN authentication
            svn_auth_result = self._add_user_to_svn_auth(username, password)
            if not svn_auth_result["success"]:
                logger.warning(f"Failed to add {username} to SVN authentication: {svn_auth_result.get('error')}")
            
            result["success"] = True
            result["message"] = f"SSH user '{username}' created successfully"
            result["svn_auth"] = svn_auth_result["success"]
            logger.info(f"Created SSH user: {username}")
            
        except Exception as e:
            result["error"] = f"Unexpected error: {str(e)}"
            logger.error(f"Error creating SSH user {username}: {e}")
        
        return result
    
    def _add_user_to_svn_auth(self, username: str, password: str) -> Dict[str, Any]:
        """
        Add a user to SVN authentication system
        This adds the user to the SVN passwd file so they can commit
        """
        result = {
            "success": False,
            "message": "",
            "error": None
        }
        
        try:
            # Check if user already exists in SVN passwd file
            check_cmd = ["docker", "exec", "automark-svn", "grep", f"^{username} =", "/etc/subversion/passwd"]
            check_result = subprocess.run(check_cmd, capture_output=True, text=True)
            
            if check_result.returncode == 0:
                result["success"] = True
                result["message"] = f"User {username} already exists in SVN authentication"
                return result
            
            # Add user to SVN passwd file
            add_cmd = [
                "docker", "exec", "automark-svn",
                "bash", "-c", f"echo '{username} = {password}' >> /etc/subversion/passwd"
            ]
            add_result = subprocess.run(add_cmd, capture_output=True, text=True, timeout=10)
            
            if add_result.returncode != 0:
                result["error"] = f"Failed to add user to SVN passwd: {add_result.stderr}"
                return result
            
            # Add user to students group in authz file
            authz_cmd = [
                "docker", "exec", "automark-svn",
                "bash", "-c", f"""
                # Check if students group is empty and add user appropriately
                if grep -q '^students = $' /etc/subversion/authz; then
                    # Students group is empty, add first user
                    sed -i 's/^students = $/students = {username}/' /etc/subversion/authz
                else
                    # Add to existing students group
                    sed -i 's/^students = .*/&,{username}/' /etc/subversion/authz
                    # Clean up any double commas
                    sed -i 's/,,/,/g' /etc/subversion/authz
                fi
                """
            ]
            authz_result = subprocess.run(authz_cmd, capture_output=True, text=True, timeout=10)
            
            if authz_result.returncode != 0:
                logger.warning(f"Failed to update authz file for {username}: {authz_result.stderr}")
            
            result["success"] = True
            result["message"] = f"Added {username} to SVN authentication"
            logger.info(f"Added {username} to SVN authentication system")
            
        except subprocess.TimeoutExpired:
            result["error"] = "SVN authentication update timed out"
        except Exception as e:
            result["error"] = f"Error updating SVN authentication: {str(e)}"
            logger.error(f"Error adding {username} to SVN auth: {e}")
        
        return result
    
    def delete_user(self, username: str) -> Dict[str, Any]:
        """
        Delete an SSH user from the container
        Returns dict with success status and details
        """
        result = {
            "success": False,
            "username": username,
            "message": "",
            "error": None
        }
        
        # Check if user exists
        if not self.user_exists(username):
            result["message"] = f"User '{username}' does not exist"
            result["success"] = True  # Not an error, user doesn't exist
            return result

    def delete_user(self, username: str) -> Dict[str, Any]:
        result = {"success": False, "username": username, "message": "", "error": None}
        try:
            if not self.user_exists(username):
                result["success"] = True
                result["message"] = f"User '{username}' does not exist"
                return result

            code, out = self._exec_sh(f"userdel -r {username}")
            if code != 0:
                result["error"] = f"Failed to delete user: {out}"
                return result

            result["success"] = True
            result["message"] = f"SSH user '{username}' deleted successfully"
            logger.info(result["message"])
            return result

        except Exception as e:
            logger.exception("Unexpected error deleting SSH user")
            result["error"] = f"Unexpected error: {e}"
            return result

    def list_users(self) -> Dict[str, Any]:
        result = {"success": False, "users": [], "error": None}
        try:
            # list non-system users (uid >= 1000)
            code, out = self._exec_sh(r"""awk -F: '$3 >= 1000 {print $1}' /etc/passwd""")
            if code != 0:
                result["error"] = f"Failed to list users: {out}"
                return result
            users = [u.strip() for u in out.splitlines() if u.strip()]
            result["success"] = True
            result["users"] = users
            return result
        except Exception as e:
            logger.exception("Unexpected error listing users")
            result["error"] = f"Unexpected error: {e}"
            return result


# helper for FastAPI register flow
def create_ssh_user_for_registration(username: str, password: str) -> Dict[str, Any]:
    manager = SSHUserManager()
    return manager.create_user(username, password)

def add_existing_user_to_svn(username: str, password: str) -> Dict[str, Any]:
    """Add an existing SSH user to SVN authentication system"""
    manager = SSHUserManager()
    return manager._add_user_to_svn_auth(username, password)

def create_student_submission_repo(username: str, assignment_path: str) -> Dict[str, Any]:
    """
    Create a student submission repository for an assignment
    assignment_path example: "2025-AUT-Comp0067-Assignment1"
    """
    result = {
        "success": False,
        "message": "",
        "error": None
    }
    
    try:
        student_repo_path = f"student-repos/{assignment_path}/{username}"
        
        # Create student submission directory in SVN
        cmd = [
            "docker", "exec", "automark-svn",
            "bash", "-c", f"""
            # Check out the main repository
            svn checkout file:///var/svn/repositories/automark /tmp/svn-student-setup --force
            
            # Create student directory structure
            mkdir -p "/tmp/svn-student-setup/{student_repo_path}"
            
            # Add to SVN
            cd /tmp/svn-student-setup
            svn add "{student_repo_path}" --parents
            
            # Commit the new student repository
            svn commit -m "Create submission repository for {username} - {assignment_path}" --username admin --password adminpass123 --no-auth-cache
            
            # Clean up
            rm -rf /tmp/svn-student-setup
            """
        ]
        
        cmd_result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if cmd_result.returncode != 0:
            result["error"] = f"Failed to create student repository: {cmd_result.stderr}"
            return result
        
        result["success"] = True
        result["message"] = f"Created submission repository: {student_repo_path}"
        result["repo_path"] = student_repo_path
        
    except subprocess.TimeoutExpired:
        result["error"] = "Student repository creation timed out"
    except Exception as e:
        result["error"] = f"Error creating student repository: {str(e)}"
    
    return result

def update_user_directories(username: str) -> Dict[str, Any]:
    """
    Update SSH user directories based on their subject enrollments
    """
    import sqlite3
    import os
    
    result = {
        "success": False,
        "username": username,
        "message": "",
        "error": None
    }
    
    try:
        # Get database path from environment or default
        db_path = os.getenv("DB_PATH", "/app/data/automark.db")
        
        # Connect to database and get user enrollments
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Get user ID
        c.execute("SELECT id FROM users WHERE username = ?", (username,))
        user_result = c.fetchone()
        if not user_result:
            result["error"] = f"User {username} not found in database"
            return result
        
        user_id = user_result[0]
        
        # Get user's active enrollments
        c.execute("""
            SELECT se.semester, se.year, s.code
            FROM subject_enrollments se
            JOIN subjects s ON se.subject_id = s.id
            WHERE se.student_id = ? AND se.status = 'active'
            ORDER BY se.year, se.semester, s.code
        """, (user_id,))
        
        enrollments = c.fetchall()
        
        if not enrollments:
            conn.close()
            result["success"] = True
            result["message"] = "No enrollments found - directories unchanged"
            return result
        
        # Create directories for each enrollment
        manager = SSHUserManager()
        directories_created = []
        
        for semester, year, subject_code in enrollments:
            # Create subject directory structure
            subject_path = f"/home/{username}/{year}/{semester}/{subject_code}"
            
            # Get actual assignment templates for this subject from database
            c.execute("""
                SELECT at.assignment_number, at.name, at.status
                FROM assignment_templates at
                JOIN subjects s ON at.subject_id = s.id
                WHERE s.code = ? AND at.semester = ? AND at.year = ? AND at.status IN ('draft', 'published')
                ORDER BY at.assignment_number
            """, (subject_code, semester, year))
            
            assignment_templates = c.fetchall()
            
            if not assignment_templates:
                logger.info(f"No assignment templates found for {subject_code} {semester} {year} - creating base subject directory only")
                # Create just the subject directory if no assignments exist yet
                success, stdout, stderr = manager._exec_in_container([
                    "bash", "-c", f"""
                    if [ ! -d "{subject_path}" ]; then
                        mkdir -p "{subject_path}"
                        chown "{username}:{username}" "{subject_path}"
                        chmod 755 "{subject_path}"
                        echo "Created base directory: {subject_path}"
                    fi
                    """
                ])
                if success:
                    directories_created.append(subject_path)
                continue
            
            # Create directories only for assignments that actually exist
            for assignment_number, assignment_name, status in assignment_templates:
                assignment_path = f"{subject_path}/Assignment{assignment_number}"
                
                success, stdout, stderr = manager._exec_in_container([
                    "bash", "-c", f"""
                    # Create assignment directory if it doesn't exist
                    if [ ! -d "{assignment_path}" ]; then
                        mkdir -p "{assignment_path}"
                        chown "{username}:{username}" "{assignment_path}"
                        chmod 755 "{assignment_path}"
                        echo "Created: {assignment_path} ({assignment_name})"
                    else
                        echo "Exists: {assignment_path} ({assignment_name})"
                    fi
                    """
                ])
                
                if success:
                    directories_created.append(assignment_path)
                else:
                    logger.warning(f"Failed to create directory {assignment_path}: {stderr}")
        
        # Update welcome message with available subjects and ensure ALL permissions are correct
        subject_list = ", ".join([f"{sem}/{code}" for sem, year, code in enrollments])
        success, stdout, stderr = manager._exec_in_container([
            "bash", "-c", f"""
            # Update .bashrc with current enrollments
            grep -v "enrolled subjects" "/home/{username}/.bashrc" > "/tmp/{username}_bashrc" 2>/dev/null || true
            mv "/tmp/{username}_bashrc" "/home/{username}/.bashrc" 2>/dev/null || true
            echo 'echo "📚 Your enrolled subjects: {subject_list}"' >> "/home/{username}/.bashrc"
            echo 'echo "💡 Tip: cd ~/2025/AUT/Comp0067/Assignment1 && svn checkout [template] ."' >> "/home/{username}/.bashrc"
            
            # CRITICAL FIX: Ensure ALL user directories and files are owned by the student user
            # This fixes SVN working copy permission issues
            chown -R "{username}:{username}" "/home/{username}"
            
            # Ensure proper permissions for student operations
            chmod 755 "/home/{username}"
            find "/home/{username}" -type d -exec chmod 755 {{}} \\;
            find "/home/{username}" -type f -exec chmod 644 {{}} \\;
            
            # Make .bashrc executable
            chmod 644 "/home/{username}/.bashrc"
            """
        ])
        
        result["success"] = True
        result["message"] = f"Updated directories for {len(directories_created)} assignments across {len(enrollments)} subjects"
        logger.info(f"Updated SSH directories for {username}: {subject_list}")
        
    except Exception as e:
        result["error"] = f"Unexpected error: {str(e)}"
        logger.error(f"Error updating directories for {username}: {e}")
    finally:
        if 'conn' in locals():
            conn.close()
    
    return result

if __name__ == "__main__":
    # Optional quick manual test:
    import sys
    if len(sys.argv) < 2:
        print("Usage: python ssh_user_manager.py [create <u> <p> | delete <u> | list]")
        sys.exit(1)
    action = sys.argv[1]
    mgr = SSHUserManager()
    if action == "create" and len(sys.argv) == 4:
        print(mgr.create_user(sys.argv[2], sys.argv[3]))
    elif action == "delete" and len(sys.argv) == 3:
        print(mgr.delete_user(sys.argv[2]))
    elif action == "list":
        print(mgr.list_users())
    else:
        print("Usage: python ssh_user_manager.py [create <u> <p> | delete <u> | list]")
        sys.exit(1)
