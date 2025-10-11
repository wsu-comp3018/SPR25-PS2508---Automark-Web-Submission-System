// databaseview.js - No authentication required
const API_BASE = "/api/v1";
let users = [];

// DOM elements
const tableBody = document.querySelector('#userTable tbody');
const selectAllCheckbox = document.getElementById('selectAll');

// Load users from backend
async function loadUsers() {
    try {
        showLoading();
        const response = await fetch(`${API_BASE}/users/public`);
        
        if (!response.ok) {
            throw new Error(`Failed to load users: ${response.status}`);
        }
        
        users = await response.json();
        renderUsers();
    } catch (error) {
        console.error('Error loading users:', error);
        alert('Failed to load users. Please try again.');
        tableBody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:#ff4757;">Error loading users: ${error.message}</td></tr>`;
    }
}

// Render users in table
function renderUsers() {
    tableBody.innerHTML = "";

    if (users.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:#999;">No users found.</td></tr>`;
        return;
    }

    users.forEach((user, index) => {
        const row = document.createElement('tr');
        const createdAt = user.created_at ? new Date(user.created_at) : new Date();
        const statusClass = user.is_active ? 'status-active' : 'status-inactive';
        const statusText = user.is_active ? 'Active' : 'Inactive';

        row.innerHTML = `
            <td><input type="checkbox" class="user-checkbox" data-user-id="${user.id}"></td>
            <td>${index + 1}</td>
            <td>${user.username}</td>
            <td>${user.email}</td>
            <td>${user.role}</td>
            <td>${user.first_name} ${user.last_name}</td>
            <td class="${statusClass}">${statusText}</td>
            <td>${createdAt.toLocaleString()}</td>
        `;

        tableBody.appendChild(row);
    });
}

// Delete selected users (disabled for public access)
function deleteSelectedUsers() {
    alert("User deletion is disabled for public access. Please login as a lecturer to manage users.");
}

// Reset database (disabled for public access)
function resetDatabase() {
    alert("Database reset is disabled for public access. Please login as a lecturer to perform this action.");
}

// Show loading state
function showLoading() {
    tableBody.innerHTML = `
        <tr>
            <td colspan="8" style="text-align:center;">
                <div style="display: flex; align-items: center; justify-content: center; padding: 20px;">
                    <div style="width: 20px; height: 20px; border: 2px solid #f3f3f3; border-top: 2px solid #007bff; border-radius: 50%; animation: spin 1s linear infinite; margin-right: 10px;"></div>
                    Loading users...
                </div>
            </td>
        </tr>
    `;
}

// Add CSS animation for spinner
const style = document.createElement('style');
style.textContent = `
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    .status-active { color: green; font-weight: bold; }
    .status-inactive { color: red; font-weight: bold; }
`;
document.head.appendChild(style);

// Event listeners
selectAllCheckbox.addEventListener('change', function() {
    const checkboxes = document.querySelectorAll('.user-checkbox');
    checkboxes.forEach(cb => cb.checked = this.checked);
});

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    loadUsers();
});

// Make functions available globally for HTML onclick handlers
window.deleteSelectedUsers = deleteSelectedUsers;
window.resetDatabase = resetDatabase;