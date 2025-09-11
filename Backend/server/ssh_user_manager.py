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
                chown "{username}:{username}" "/home/{username}/.bashrc"
                """
            )
            if code != 0:
                result["error"] = f"Failed to set up user environment: {out}"
                return result

            result["success"] = True
            result["message"] = f"SSH user '{username}' created successfully"
            logger.info(result["message"])
            return result

        except Exception as e:
            logger.exception("Unexpected error creating SSH user")
            result["error"] = f"Unexpected error: {e}"
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
