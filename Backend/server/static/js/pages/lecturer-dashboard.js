// lecturer-dashboard.js - Complete integration with FastAPI backend
const API_BASE = "/api/v1";
let currentUser = null;
let folders = [];
let students = [];
let submissions = [];
let currentFolderView = null;

// DOM Elements
const lecturerNameEl = document.getElementById('lecturerName');
const logoutBtn = document.getElementById('logoutBtn');
const stats = {
    totalFolders: document.getElementById('totalFolders'),
    totalStudents: document.getElementById('totalStudents'),
    totalSubmissions: document.getElementById('totalSubmissions'),
    pendingReview: document.getElementById('pendingReview')
};

// Initialize dashboard
async function initializeDashboard() {
    // Check authentication
    const token = localStorage.getItem('automark_token');
    const userData = localStorage.getItem('automark_user');
    
    if (!token || !userData) {
        window.location.href = '/';
        return;
    }
    
    currentUser = JSON.parse(userData);
    if (currentUser.role !== 'lecturer') {
        window.location.href = '/dashboard';
        return;
    }
    
    // Update UI
    lecturerNameEl.textContent = `Welcome, ${currentUser.firstName} ${currentUser.lastName}`;
    logoutBtn.addEventListener('click', handleLogout);
    
    // Load initial data
    await loadAllData();
    setupEventListeners();
}

// Load all required data
async function loadAllData() {
    try {
        showLoading();
        await Promise.all([
            loadFolders(),
            loadStudents(),
            loadSubmissions()
        ]);
        updateStats();
        renderFolderList();
        renderStudentSearch();
    } catch (error) {
        console.error('Error loading data:', error);
        showNotification('Failed to load data. Please refresh.', 'error');
    } finally {
        hideLoading();
    }
}

// API Functions
async function loadFolders() {
    try {
        const response = await fetch(`${API_BASE}/folders`, {
            headers: getAuthHeaders()
        });
        
        if (response.status === 401) {
            handleAuthError();
            return;
        }
        
        if (!response.ok) {
            throw new Error(`Failed to load folders: ${response.status}`);
        }
        
        folders = await response.json();
    } catch (error) {
        console.error('Error loading folders:', error);
        throw error;
    }
}

async function loadStudents() {
    try {
        const response = await fetch(`${API_BASE}/students`, {
            headers: getAuthHeaders()
        });
        
        if (response.status === 401) {
            handleAuthError();
            return;
        }
        
        if (!response.ok) {
            throw new Error(`Failed to load students: ${response.status}`);
        }
        
        students = await response.json();
    } catch (error) {
        console.error('Error loading students:', error);
        throw error;
    }
}

async function loadSubmissions() {
    try {
        const response = await fetch(`${API_BASE}/submissions`, {
            headers: getAuthHeaders()
        });
        
        if (response.status === 401) {
            handleAuthError();
            return;
        }
        
        if (!response.ok) {
            throw new Error(`Failed to load submissions: ${response.status}`);
        }
        
        submissions = await response.json();
    } catch (error) {
        console.error('Error loading submissions:', error);
        throw error;
    }
}

async function createFolder(folderData) {
    try {
        const response = await fetch(`${API_BASE}/folders`, {
            method: 'POST',
            headers: getAuthHeaders('json'),
            body: JSON.stringify(folderData)
        });
        
        if (response.status === 401) {
            handleAuthError();
            return null;
        }
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to create folder');
        }
        
        return await response.json();
    } catch (error) {
        console.error('Error creating folder:', error);
        throw error;
    }
}

async function updateFolder(folderId, folderData) {
    try {
        const response = await fetch(`${API_BASE}/folders/${folderId}`, {
            method: 'PUT',
            headers: getAuthHeaders('json'),
            body: JSON.stringify(folderData)
        });
        
        if (response.status === 401) {
            handleAuthError();
            return null;
        }
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to update folder');
        }
        
        return await response.json();
    } catch (error) {
        console.error('Error updating folder:', error);
        throw error;
    }
}

async function deleteFolder(folderId) {
    try {
        const response = await fetch(`${API_BASE}/folders/${folderId}`, {
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        
        if (response.status === 401) {
            handleAuthError();
            return false;
        }
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to delete folder');
        }
        
        return true;
    } catch (error) {
        console.error('Error deleting folder:', error);
        throw error;
    }
}

async function gradeSubmission(submissionId, gradeData) {
    try {
        const response = await fetch(`${API_BASE}/submissions/${submissionId}/grade`, {
            method: 'POST',
            headers: getAuthHeaders('json'),
            body: JSON.stringify(gradeData)
        });
        
        if (response.status === 401) {
            handleAuthError();
            return null;
        }
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to grade submission');
        }
        
        return await response.json();
    } catch (error) {
        console.error('Error grading submission:', error);
        throw error;
    }
}

// UI Rendering Functions
function renderFolderList() {
    const folderList = document.getElementById('folderList');
    if (!folderList) return;
    
    if (folders.length === 0) {
        folderList.innerHTML = `
            <div class="empty-state">
                <h4>No folders yet</h4>
                <p>Create your first assignment folder to get started.</p>
            </div>
        `;
        return;
    }
    
    folderList.innerHTML = folders.map(folder => `
        <div class="folder-item" data-folder-id="${folder.id}">
            <div class="folder-header">
                <div class="folder-info">
                    <h4>${folder.name}</h4>
                    <div class="folder-meta">
                        <span class="status-badge ${folder.status}">${folder.status}</span>
                        <span>Due: ${folder.due_date ? new Date(folder.due_date).toLocaleDateString() : 'No due date'}</span>
                        <span>${folder.assigned_students_count || 0} students assigned</span>
                    </div>
                </div>
                <div class="folder-actions">
                    <button class="icon-btn view-subs" title="View submissions">📋</button>
                    <button class="icon-btn edit-folder" title="Edit folder">✏️</button>
                    <button class="icon-btn delete-folder" title="Delete folder">🗑️</button>
                </div>
            </div>
            <div class="folder-details" style="display: none;">
                <p>${folder.description || 'No description'}</p>
                <div class="assigned-students">
                    <strong>Assigned to:</strong> ${folder.assigned_students_count || 0} students
                </div>
            </div>
        </div>
    `).join('');
    
    // Add event listeners to folder items
    document.querySelectorAll('.folder-item').forEach(item => {
        item.querySelector('.folder-header').addEventListener('click', (e) => {
            if (!e.target.closest('.folder-actions')) {
                toggleFolderDetails(item);
            }
        });
        
        item.querySelector('.view-subs').addEventListener('click', (e) => {
            e.stopPropagation();
            const folderId = item.dataset.folderId;
            viewSubmissions(folderId);
        });
        
        item.querySelector('.edit-folder').addEventListener('click', (e) => {
            e.stopPropagation();
            const folderId = item.dataset.folderId;
            editFolder(folderId);
        });
        
        item.querySelector('.delete-folder').addEventListener('click', (e) => {
            e.stopPropagation();
            const folderId = item.dataset.folderId;
            deleteFolderPrompt(folderId);
        });
    });
}

function renderStudentSearch() {
    const assignUserList = document.getElementById('assignUserList');
    if (!assignUserList) return;
    
    assignUserList.innerHTML = students.map(student => `
        <label class="student-checkbox">
            <input type="checkbox" name="assignedStudents" value="${student.id}">
            ${student.first_name} ${student.last_name} (${student.username})
        </label>
    `).join('');
}

function updateStats() {
    stats.totalFolders.textContent = folders.length;
    stats.totalStudents.textContent = students.length;
    stats.totalSubmissions.textContent = submissions.length;
    stats.pendingReview.textContent = submissions.filter(s => s.status === 'submitted').length;
}

// Event Handlers
function setupEventListeners() {
    // Create folder form
    const createFolderBtn = document.getElementById('createFolderBtn');
    if (createFolderBtn) {
        createFolderBtn.addEventListener('click', handleCreateFolder);
    }
    
    // Reset form
    const resetFoldersBtn = document.getElementById('resetFoldersBtn');
    if (resetFoldersBtn) {
        resetFoldersBtn.addEventListener('click', resetFolderForm);
    }
    
    // Quick actions
    document.getElementById('showAllSubs')?.addEventListener('click', showAllSubmissions);
    document.getElementById('exportData')?.addEventListener('click', exportData);
    document.getElementById('bulkAssign')?.addEventListener('click', showBulkAssignModal);
    
    // Expand/Collapse buttons
    document.getElementById('expandAllBtn')?.addEventListener('click', expandAllFolders);
    document.getElementById('collapseAllBtn')?.addEventListener('click', collapseAllFolders);
}

async function handleCreateFolder() {
    const folderData = {
        name: document.getElementById('newFolderName').value.trim(),
        description: document.getElementById('folderDescription').value.trim(),
        due_date: document.getElementById('folderDueDate').value,
        max_points: parseInt(document.getElementById('folderMaxPoints').value) || 100,
        status: document.getElementById('folderStatus').value,
        student_ids: Array.from(document.querySelectorAll('input[name="assignedStudents"]:checked'))
            .map(checkbox => parseInt(checkbox.value))
    };
    
    if (!folderData.name) {
        showNotification('Folder name is required', 'error');
        return;
    }
    
    try {
        const newFolder = await createFolder(folderData);
        if (newFolder) {
            showNotification('Folder created successfully', 'success');
            resetFolderForm();
            await loadAllData(); // Reload data
        }
    } catch (error) {
        showNotification(error.message, 'error');
    }
}

function handleLogout() {
    localStorage.removeItem('automark_token');
    localStorage.removeItem('automark_user');
    window.location.href = '/';
}

// Utility Functions
function getAuthHeaders(contentType = null) {
    const headers = {
        'Authorization': `Bearer ${localStorage.getItem('automark_token')}`
    };
    
    if (contentType === 'json') {
        headers['Content-Type'] = 'application/json';
    }
    
    return headers;
}

function handleAuthError() {
    showNotification('Session expired. Please login again.', 'error');
    setTimeout(() => {
        handleLogout();
    }, 2000);
}

function showNotification(message, type = 'info') {
    const notification = document.getElementById('notification');
    if (notification) {
        notification.textContent = message;
        notification.className = `notification ${type}`;
        notification.style.display = 'block';
        
        setTimeout(() => {
            notification.style.display = 'none';
        }, 3000);
    }
}

function showLoading() {
    // Implement loading indicator
    document.body.style.cursor = 'wait';
}

function hideLoading() {
    document.body.style.cursor = 'default';
}

// Placeholder functions for unimplemented features
function toggleFolderDetails(item) {
    const details = item.querySelector('.folder-details');
    details.style.display = details.style.display === 'none' ? 'block' : 'none';
}

function viewSubmissions(folderId) {
    const folder = folders.find(f => f.id == folderId);
    if (folder) {
        currentFolderView = folderId;
        // Show submissions view
        document.getElementById('subViewer').style.display = 'block';
        document.getElementById('subViewerFolderName').textContent = folder.name;
        renderSubmissions(folderId);
    }
}

function renderSubmissions(folderId) {
    const folderSubmissions = submissions.filter(s => s.folder_id == folderId);
    const container = document.getElementById('submissionsContainer');
    
    if (folderSubmissions.length === 0) {
        container.innerHTML = '<p>No submissions yet.</p>';
        return;
    }
    
    container.innerHTML = folderSubmissions.map(sub => `
        <div class="submission-item">
            <div class="submission-info">
                <strong>${getStudentName(sub.student_id)}</strong>
                <span>Submitted: ${new Date(sub.submitted_at).toLocaleString()}</span>
                <span class="status-badge ${sub.status}">${sub.status}</span>
            </div>
            <div class="submission-actions">
                <button class="grade-btn" data-submission-id="${sub.id}">Grade</button>
            </div>
        </div>
    `).join('');
}

function getStudentName(studentId) {
    const student = students.find(s => s.id == studentId);
    return student ? `${student.first_name} ${student.last_name}` : 'Unknown Student';
}

function resetFolderForm() {
    document.getElementById('newFolderName').value = '';
    document.getElementById('folderDescription').value = '';
    document.getElementById('folderDueDate').value = '';
    document.getElementById('folderMaxPoints').value = '100';
    document.getElementById('folderStatus').value = 'draft';
    document.querySelectorAll('input[name="assignedStudents"]').forEach(checkbox => {
        checkbox.checked = false;
    });
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', initializeDashboard);

// Export functions for HTML onclick handlers
window.deleteSelectedUsers = () => showNotification('Please use the individual folder actions', 'info');
window.resetDatabase = () => showNotification('Database reset is available in the database view', 'info');