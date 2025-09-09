#!/usr/bin/env python3
"""
SSH User Management Script
Manages SSH users in the automark-ssh container via docker exec
"""

import subprocess
import logging
import os
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class SSHUserManager:
    def __init__(self, container_name: str = "automark-ssh"):
        self.container_name = container_name
    
    def _exec_in_container(self, command: list[str]) -> tuple[bool, str, str]:
        """
        Execute a command in the SSH container
        Returns: (success, stdout, stderr)
        """
        try:
            cmd = ["docker", "exec", self.container_name] + command
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=30
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", "Command timed out"
        except Exception as e:
            return False, "", str(e)
    
    def user_exists(self, username: str) -> bool:
        """Check if a user already exists in the SSH container"""
        success, stdout, stderr = self._exec_in_container(["id", username])
        return success
    
    def create_user(self, username: str, password: str) -> Dict[str, Any]:
        """
        Create a new SSH user in the container
        Returns dict with success status and details
        """
        result = {
            "success": False,
            "username": username,
            "message": "",
            "error": None
        }
        
        # Check if user already exists
        if self.user_exists(username):
            result["message"] = f"User '{username}' already exists"
            result["success"] = True  # Not an error, user exists
            return result
        
        try:
            # Create the user with normal home directory
            success, stdout, stderr = self._exec_in_container([
                "useradd", "-m", "-s", "/bin/bash", username
            ])
            
            if not success:
                result["error"] = f"Failed to create user: {stderr}"
                return result
            
            # Set password
            success, stdout, stderr = self._exec_in_container([
                "bash", "-c", f"echo '{username}:{password}' | chpasswd"
            ])
            
            if not success:
                result["error"] = f"Failed to set password: {stderr}"
                return result
            
            # Create simple assignment directory structure  
            success, stdout, stderr = self._exec_in_container([
                "bash", "-c", f"""
                # Create assignment directories directly in user home
                mkdir -p "/home/{username}/2025/AUT/PX/Assignment1" \\
                         "/home/{username}/2025/AUT/PX/Assignment2" \\
                         "/home/{username}/2025/SPR/PX/Assignment1" \\
                         "/home/{username}/2025/SPR/PX/Assignment2"
                
                # Set proper ownership and permissions
                chown -R "{username}:{username}" "/home/{username}/2025"
                chmod 755 "/home/{username}/2025"
                chmod -R 755 "/home/{username}/2025"
                chmod 775 "/home/{username}/2025/AUT/PX/Assignment1" "/home/{username}/2025/AUT/PX/Assignment2" \\
                          "/home/{username}/2025/SPR/PX/Assignment1" "/home/{username}/2025/SPR/PX/Assignment2"
                """
            ])
            
            if not success:
                result["error"] = f"Failed to create chroot directories: {stderr}"
                return result
            
            # Simple welcome message setup
            success, stdout, stderr = self._exec_in_container([
                "bash", "-c", f"""
                # Create a simple welcome message
                echo 'echo "Welcome to Automark, {username}! Your assignment folders are in ~/2025/"' >> "/home/{username}/.bashrc"
                chown "{username}:{username}" "/home/{username}/.bashrc"
                """
            ])
            
            if not success:
                result["error"] = f"Failed to set up user environment: {stderr}"
                return result
            
            result["success"] = True
            result["message"] = f"SSH user '{username}' created successfully"
            logger.info(f"Created SSH user: {username}")
            
        except Exception as e:
            result["error"] = f"Unexpected error: {str(e)}"
            logger.error(f"Error creating SSH user {username}: {e}")
        
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
        
        try:
            # Delete user and home directory
            success, stdout, stderr = self._exec_in_container([
                "userdel", "-r", username
            ])
            
            if not success:
                result["error"] = f"Failed to delete user: {stderr}"
                return result
            
            result["success"] = True
            result["message"] = f"SSH user '{username}' deleted successfully"
            logger.info(f"Deleted SSH user: {username}")
            
        except Exception as e:
            result["error"] = f"Unexpected error: {str(e)}"
            logger.error(f"Error deleting SSH user {username}: {e}")
        
        return result
    
    def list_users(self) -> Dict[str, Any]:
        """
        List all non-system users in the SSH container
        Returns dict with user list
        """
        result = {
            "success": False,
            "users": [],
            "error": None
        }
        
        try:
            # Get users with UID >= 1000 (non-system users)
            success, stdout, stderr = self._exec_in_container([
                "bash", "-c", "awk -F: '$3 >= 1000 {print $1}' /etc/passwd"
            ])
            
            if not success:
                result["error"] = f"Failed to list users: {stderr}"
                return result
            
            users = [user.strip() for user in stdout.split('\n') if user.strip()]
            result["success"] = True
            result["users"] = users
            
        except Exception as e:
            result["error"] = f"Unexpected error: {str(e)}"
            logger.error(f"Error listing SSH users: {e}")
        
        return result

# Helper function for FastAPI integration
def create_ssh_user_for_registration(username: str, password: str) -> Dict[str, Any]:
    """
    Convenience function to create SSH user after web registration
    """
    manager = SSHUserManager()
    return manager.create_user(username, password)

if __name__ == "__main__":
    # Test the functionality
    import sys
    
    if len(sys.argv) != 4:
        print("Usage: python ssh_user_manager.py <create|delete|list> <username> <password>")
        sys.exit(1)
    
    action = sys.argv[1]
    username = sys.argv[2] if len(sys.argv) > 2 else ""
    password = sys.argv[3] if len(sys.argv) > 3 else ""
    
    manager = SSHUserManager()
    
    if action == "create":
        result = manager.create_user(username, password)
        print(f"Result: {result}")
    elif action == "delete":
        result = manager.delete_user(username)
        print(f"Result: {result}")
    elif action == "list":
        result = manager.list_users()
        print(f"Result: {result}")
    else:
        print("Invalid action. Use 'create', 'delete', or 'list'")
        sys.exit(1)
