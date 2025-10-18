"""
Filesystem-first file storage module for AutoMark
Stores files on filesystem with metadata in database
"""
import os
import shutil
import hashlib
import base64
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Base directories for file storage
FILES_BASE = Path(os.getenv("FILES_BASE", "/app/data/files"))
ASSIGN_BASE = Path(os.getenv("ASSIGN_BASE", "/app/data/assignments"))

# Ensure base directories exist
FILES_BASE.mkdir(parents=True, exist_ok=True)
ASSIGN_BASE.mkdir(parents=True, exist_ok=True)


def save_file_to_disk(
    name: str,
    content_b64: str,
    file_type: str = "application/octet-stream",
    subdir: str = "uploads"
) -> Dict[str, Any]:
    """
    Save a base64-encoded file to the filesystem.
    
    Args:
        name: Original filename
        content_b64: Base64-encoded file content (may include data URL prefix)
        file_type: MIME type of the file
        subdir: Subdirectory under FILES_BASE (e.g., 'uploads', 'markers')
    
    Returns:
        Dict with: name, file_path, size, checksum
    
    Raises:
        ValueError: If content cannot be decoded
    """
    try:
        # Handle data URLs (e.g., "data:text/plain;base64,SGVsbG8=")
        if "," in content_b64:
            content_b64 = content_b64.split(",", 1)[1]
        
        # Decode base64 content
        content_bytes = base64.b64decode(content_b64)
    except Exception as e:
        raise ValueError(f"Failed to decode file content: {e}")
    
    # Generate unique filename using hash to avoid collisions
    file_hash = hashlib.sha256(content_bytes).hexdigest()[:16]
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
    unique_name = f"{file_hash}_{safe_name}"
    
    # Create destination path
    dest_dir = FILES_BASE / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / unique_name
    
    # Write file
    dest_path.write_bytes(content_bytes)
    
    # Make scripts executable
    if name.endswith(('.sh', '.py', '.bash')):
        os.chmod(dest_path, 0o755)
        logger.info(f"Made file executable: {dest_path}")
    
    return {
        "name": name,
        "file_path": str(dest_path),
        "size": len(content_bytes),
        "checksum": file_hash,
        "type": file_type
    }


def copy_marker_files_to_assignment(
    file_paths: List[str],
    folder_id: int
) -> Path:
    """
    Copy marker files to the assignment's marker directory.
    
    Args:
        file_paths: List of source file paths
        folder_id: Assignment folder ID
    
    Returns:
        Path to the marker directory
    """
    marker_dir = ASSIGN_BASE / str(folder_id) / "marker"
    marker_dir.mkdir(parents=True, exist_ok=True)
    
    for source_path_str in file_paths:
        source_path = Path(source_path_str)
        if not source_path.exists():
            logger.warning(f"Source file not found: {source_path}")
            continue
        
        # Copy to marker directory as markerscript.sh (standardized name)
        dest_path = marker_dir / "markerscript.sh"
        shutil.copy2(source_path, dest_path)
        
        # Ensure the script is executable
        os.chmod(dest_path, 0o755)
        
        logger.info(f"Copied marker file: {source_path.name} -> markerscript.sh")
    
    return marker_dir


def delete_file(file_path: str) -> bool:
    """
    Delete a file from the filesystem.
    
    Args:
        file_path: Path to the file to delete
    
    Returns:
        True if deleted, False if file didn't exist
    """
    try:
        path = Path(file_path)
        if path.exists():
            path.unlink()
            logger.info(f"Deleted file: {file_path}")
            return True
        return False
    except Exception as e:
        logger.error(f"Failed to delete file {file_path}: {e}")
        return False


def read_file_content(file_path: str) -> Optional[bytes]:
    """
    Read file content from filesystem.
    
    Args:
        file_path: Path to the file
    
    Returns:
        File content as bytes, or None if file doesn't exist
    """
    try:
        path = Path(file_path)
        if path.exists():
            return path.read_bytes()
        return None
    except Exception as e:
        logger.error(f"Failed to read file {file_path}: {e}")
        return None


def cleanup_folder_files(folder_id: int) -> None:
    """
    Clean up all files associated with a folder.
    
    Args:
        folder_id: Assignment folder ID
    """
    try:
        folder_dir = ASSIGN_BASE / str(folder_id)
        if folder_dir.exists():
            shutil.rmtree(folder_dir)
            logger.info(f"Cleaned up folder {folder_id} files")
    except Exception as e:
        logger.error(f"Failed to cleanup folder {folder_id}: {e}")


def get_marker_files(folder_id: int) -> List[Dict[str, Any]]:
    """
    Get list of marker files for an assignment.
    
    Args:
        folder_id: Assignment folder ID
    
    Returns:
        List of dicts with file info: {name, path, size, is_executable}
    """
    marker_dir = ASSIGN_BASE / str(folder_id) / "marker"
    
    if not marker_dir.exists():
        return []
    
    files = []
    for file_path in marker_dir.iterdir():
        if file_path.is_file():
            stat = file_path.stat()
            files.append({
                "name": file_path.name,
                "path": str(file_path),
                "size": stat.st_size,
                "is_executable": os.access(file_path, os.X_OK),
                "modified_at": stat.st_mtime
            })
    
    return files

