// lecturer-dashboard.js - API-integrated dashboard code

// Add debug logging
console.log('🚀 Lecturer dashboard script loaded');

// Check if running in browser
if (typeof window === 'undefined') {
    console.error('❌ Script not running in browser context');
}

        const API_BASE = '/api/v1';
        const SESSION_KEY = 'automark_user';
        const TOKEN_KEY = 'automark_token';

        let isCreatingAssignment = false;

        function $(id) { return document.getElementById(id) }

        // Assignment model structure
        class Assignment {
            constructor(id, name, description, due_date, max_points, status, subject_code, student_ids) {
                this.id = id;
                this.name = name;
                this.description = description;
                this.due_date = due_date;
                this.max_points = max_points;
                this.status = status;
                this.subject_code = subject_code;
                this.student_ids = student_ids;
            }
        }

        // Global state
        let currentUser = null;
        let authToken = null;
        let allStudents = [];
        let lecturerSubjects = [];
        let allFolders = [];
        let allSubmissions = [];
        let expandedFolders = new Set();
        let filteredStudents = [];
        let currentEditingAssignment = null; // Add this to global scope

        // Utility functions
        function showNotification(message, type = 'success') {
            const notification = $('notification');
            if (!notification) return;
            notification.textContent = message;
            notification.className = `notification ${type} show`;
            setTimeout(() => {
                notification.classList.remove('show');
            }, 3000);
        }

        // API Helper function
       async function apiCall(endpoint, options = {}) {
    try {
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
            }
        };
        
        if (authToken) {
            defaultOptions.headers['Authorization'] = `Bearer ${authToken}`;
        }
        
        console.log(`Making API call to: ${API_BASE}${endpoint}`, options);
        
        const response = await fetch(`${API_BASE}${endpoint}`, {
            ...defaultOptions,
            ...options,
            headers: { ...defaultOptions.headers, ...options.headers }
        });
        
        console.log(`API Response status: ${response.status}`);
        
        if (!response.ok) {
            let errorDetail;
            try {
                const errorData = await response.json();
                errorDetail = errorData.detail || errorData.message || `HTTP ${response.status}`;
            } catch {
                errorDetail = `HTTP ${response.status} - ${response.statusText}`;
            }
            throw new Error(errorDetail);
        }
        
        const data = await response.json();
        console.log(`API Response data:`, data);
        return data;
        
    } catch (error) {
        console.error('API call failed:', endpoint, error);
        
        // Provide more specific error messages
        if (error.name === 'TypeError' && error.message.includes('fetch')) {
            throw new Error('Network error - please check your connection');
        }
        
        throw error;
    }
}

        // Authentication functions
        function logout() {
            localStorage.removeItem(SESSION_KEY);
            localStorage.removeItem(TOKEN_KEY);
            window.location.href = '/';
        }

        // Enhanced authentication check
        async function checkAuth() {
            const token = localStorage.getItem(TOKEN_KEY);
            const userData = localStorage.getItem(SESSION_KEY);
            
            console.log('🔐 Checking authentication...');
            console.log('Token exists:', !!token);
            console.log('User data exists:', !!userData);
            
            if (!token || !userData) {
                console.log('❌ No token or user data found, redirecting to login');
                window.location.href = '/';
                return false;
            }
            
            authToken = token;
            try {
                currentUser = JSON.parse(userData);
                console.log('👤 Current user:', currentUser);
            } catch (e) {
                console.error('❌ Failed to parse user data:', e);
                window.location.href = '/';
                return false;
            }
            
            if (currentUser.role !== 'lecturer') {
                console.log('🚫 User is not a lecturer, redirecting to student dashboard');
                window.location.href = '/studentdash.html';
                return false;
            }
            
            // Validate session with backend
            try {
                console.log('🔄 Validating session with backend...');
                const sessionValidation = await apiCall(`/auth/session/${token}`);
                console.log('✅ Session validation response:', sessionValidation);
                
                if (!sessionValidation.valid) {
                    console.log('❌ Session invalid, logging out');
                    logout();
                    return false;
                }
                
                // Update user data from session validation
                currentUser = sessionValidation.user;
                localStorage.setItem(SESSION_KEY, JSON.stringify(currentUser));
                console.log('✅ Session validated, user updated:', currentUser);
                
            } catch (error) {
                console.error('❌ Session validation failed:', error);
                logout();
                return false;
            }
            
            return true;
        }

        // Data loading functions
        async function loadAllSubjects() {
            try {
                console.log('📚 Loading subjects...');
                const allSubjects = await apiCall('/subjects');
                
                console.log('📊 All subjects received:', allSubjects);
                console.log('Current user ID:', currentUser.id, 'Type:', typeof currentUser.id);
                
                // Filter subjects for current lecturer with proper type conversion
                lecturerSubjects = allSubjects.filter(subject => {
                    const matches = subject.lecturer_id == currentUser.id || subject.lecturer_id === parseInt(currentUser.id);
                    console.log(`Checking subject ${subject.code}: lecturer_id=${subject.lecturer_id} vs user_id=${currentUser.id} -> ${matches}`);
                    return matches;
                });
                
                console.log('✅ Filtered lecturer subjects:', lecturerSubjects);
                
                if (lecturerSubjects.length === 0) {
                    console.warn('⚠️ No subjects found for this lecturer');
                    showNotification('No subjects assigned to you yet', 'warning');
                }
                
                return lecturerSubjects;
            } catch (error) {
                console.error('❌ Error loading subjects:', error);
                showNotification(`Failed to load subjects: ${error.message}`, 'error');
                return [];
            }
        }

        async function loadAllStudents() {
            try {
                const students = await apiCall('/students');
                allStudents = students;
                filteredStudents = [...students];
                return students;
            } catch (error) {
                console.error('Error loading students:', error);
                showNotification('Failed to load students', 'error');
                return [];
            }
        }

        async function loadFolders() {
            try {
                console.log('📁 Loading folders/assignments...');
                const folders = await apiCall('/folders');
                
                console.log('📊 Folders received:', folders);
                allFolders = folders;
                
                if (folders.length === 0) {
                    console.warn('⚠️ No assignments found for this lecturer');
                }
                
                return folders;
            } catch (error) {
                console.error('❌ Error loading folders:', error);
                showNotification(`Failed to load assignments: ${error.message}`, 'error');
                return [];
            }
        }

        async function loadSubmissions() {
            try {
                const submissions = await apiCall('/submissions');
                allSubmissions = submissions;
                return submissions;
            } catch (error) {
                console.error('Error loading submissions:', error);
                showNotification('Failed to load submissions', 'error');
                return [];
            }
        }

        // Enhanced data loading with sequential loading and better error handling
        async function loadAllData() {
            try {
                console.log('🔄 Loading all data sequentially...');
                
                // Load subjects first (needed for filtering)
                console.log('Step 1: Loading subjects...');
                await loadAllSubjects();
                
                // Load other data in parallel
                console.log('Step 2: Loading other data...');
                const [students, folders, submissions] = await Promise.allSettled([
                    loadAllStudents(),
                    loadFolders(),
                    loadSubmissions()
                ]);
                
                // Check results
                if (students.status === 'rejected') {
                    console.error('❌ Failed to load students:', students.reason);
                }
                if (folders.status === 'rejected') {
                    console.error('❌ Failed to load folders:', folders.reason);
                }
                if (submissions.status === 'rejected') {
                    console.error('❌ Failed to load submissions:', submissions.reason);
                }
                
                console.log('📊 Data loading summary:');
                console.log(`  - Subjects: ${lecturerSubjects.length}`);
                console.log(`  - Students: ${allStudents.length}`);
                console.log(`  - Assignments: ${allFolders.length}`);
                console.log(`  - Submissions: ${allSubmissions.length}`);
                
                // Update UI with loaded data
                renderFolderList();
                updateStatistics();
                populateCreateAssignmentModal();
                
                console.log('✅ All data loaded and UI updated');
                
                // Show success notification if we have data
                if (lecturerSubjects.length > 0 || allFolders.length > 0) {
                    showNotification('Dashboard loaded successfully!', 'success');
                } else {
                    showNotification('Dashboard loaded - no subjects or assignments found', 'warning');
                }
                
            } catch (error) {
                console.error('❌ Error in loadAllData:', error);
                showNotification('Failed to load dashboard data: ' + error.message, 'error');
            }
        }


        // Rendering functions
        function renderFolderList() {
            const folderList = $('folderList');
            if (!folderList) {
                console.error('❌ Folder list element not found');
                return;
            }
            
            console.log('🎨 Rendering folder list...');
            console.log(`  - Lecturer subjects: ${lecturerSubjects.length}`);
            console.log(`  - All folders: ${allFolders.length}`);
            
            // Store current scroll position
            const scrollTop = folderList.scrollTop;
            
            folderList.innerHTML = '';

            if (lecturerSubjects.length === 0) {
                folderList.innerHTML = `
                    <div class="folder" style="text-align: center; padding: 30px; border: 2px dashed #ddd;">
                        <div style="font-size: 24px; margin-bottom: 10px;">📚</div>
                        <div style="font-size: 16px; margin-bottom: 10px;">No subjects assigned to you yet</div>
                        <div class="muted" style="margin-bottom: 15px;">
                            Subjects will appear here once they are assigned to your account.
                        </div>
                        <button onclick="location.reload()" class="ghost">Refresh Dashboard</button>
                    </div>
                `;
                return;
            }

            lecturerSubjects.forEach(subject => {
                console.log(`🏗️ Rendering subject: ${subject.code} - ${subject.name}`);
                
                // Get assignments for this specific subject
                const subjectAssignments = allFolders.filter(folder => 
                    folder.subject_code === subject.code
                );
                
                console.log(`  - Found ${subjectAssignments.length} assignments for ${subject.code}`);
                
                const subjectElement = document.createElement('div');
                subjectElement.className = 'folder subject-folder';
                const isExpanded = expandedFolders.has(`subject_${subject.id}`);

                subjectElement.innerHTML = `
                    <div class="left">
                        <span class="folder-toggle" onclick="toggleSubjectExpansion('${subject.id}')">
                            ${isExpanded ? '▼' : '▶'}
                        </span>
                        <span class="subject-icon">📁</span>
                        <div>
                            <div class="name">${subject.code} - ${subject.name}</div>
                            <div class="meta">${subjectAssignments.length} assignment${subjectAssignments.length !== 1 ? 's' : ''}</div>
                        </div>
                    </div>
                    <div class="actions">
                        <button onclick="createAssignmentForSubject('${subject.code}')" class="success" title="Create New Assignment">
                            + Assignment
                        </button>
                        <button onclick="viewSubjectSubmissions('${subject.id}')" class="ghost" title="View All Submissions">
                            ${subjectAssignments.reduce((sum, a) => sum + (allSubmissions.filter(s => s.folder_id === a.id).length), 0)} Submissions
                        </button>
                    </div>
                `;

                folderList.appendChild(subjectElement);

                // Show assignments if expanded
                if (isExpanded) {
                    const assignmentsContainer = document.createElement('div');
                    assignmentsContainer.className = 'subfolders expanded';

                    if (subjectAssignments.length === 0) {
                        assignmentsContainer.innerHTML = `
                            <div style="padding: 20px; text-align: center; border: 1px dashed #ccc; border-radius: 8px; background: #f9f9f9;">
                                <div style="font-size: 18px; margin-bottom: 8px;">📝</div>
                                <div style="margin-bottom: 10px;">No assignments created yet for ${subject.code}</div>
                                <button onclick="createAssignmentForSubject('${subject.code}')" class="success" style="margin-top: 8px;">
                                    Create First Assignment
                                </button>
                            </div>
                        `;
                    } else {
                        // Sort assignments by creation date (newest first)
                        subjectAssignments.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
                        
                        subjectAssignments.forEach(assignment => {
                            const assignmentElement = createAssignmentElement(assignment);
                            assignmentsContainer.appendChild(assignmentElement);
                        });
                    }

                    folderList.appendChild(assignmentsContainer);
                }
            });
            
            // Restore scroll position
            folderList.scrollTop = scrollTop;
            
            console.log('✅ Folder list rendered successfully');
        }

       function createAssignmentElement(assignment) {
    const assignmentDiv = document.createElement('div');
    assignmentDiv.className = 'folder';
    assignmentDiv.dataset.assignmentId = assignment.id;
    
    const submissions = allSubmissions.filter(sub => sub.folder_id === assignment.id);
    const submissionCount = submissions.length;
    const gradedCount = submissions.filter(sub => sub.status === 'graded').length;
    
    const dueDate = assignment.due_date ? 
        new Date(assignment.due_date).toLocaleDateString() : 'No due date';
    
    const statusClass = assignment.status === 'published' ? 'active' : assignment.status;
    
    assignmentDiv.innerHTML = `
        <div class="left">
            <div>
                <div class="name">${assignment.name}</div>
                <div class="meta">
                    ${submissionCount} submissions (${gradedCount} graded) • 
                    Due: ${dueDate} • 
                    Max: ${assignment.max_points} pts
                </div>
            </div>
            <div class="status ${statusClass}">${assignment.status}</div>
        </div>
        <div class="actions">
            <button onclick="editAssignment(${assignment.id})" class="warning" title="Edit Assignment">
                ✏️ Edit
            </button>
            <button onclick="viewSubmissions(${assignment.id})" class="ghost" title="View Submissions">
                📄 ${submissionCount}
            </button>
            <button onclick="deleteAssignment(${assignment.id})" class="danger" title="Delete Assignment">
                🗑️ Delete
            </button>
        </div>
    `;
    
    return assignmentDiv;
}
        function toggleSubjectExpansion(subjectId) {
            const key = `subject_${subjectId}`;
            if (expandedFolders.has(key)) {
                expandedFolders.delete(key);
            } else {
                expandedFolders.add(key);
            }
            renderFolderList();
        }

        function updateStatistics() {
            if ($('totalFolders')) $('totalFolders').textContent = allFolders.length;
            if ($('totalStudents')) $('totalStudents').textContent = allStudents.length;
            if ($('totalSubmissions')) $('totalSubmissions').textContent = allSubmissions.length;
        }

        // Assignment creation functions
        function createAssignmentForSubject(subjectCode) {
            const modal = $('createAssignmentModal');
            if (!modal) {
                showNotification('Create assignment modal not found', 'error');
                return;
            }
            
            const subjectSelect = $('assignmentSubject');
            if (subjectSelect) {
                // Clear and populate subject dropdown
                subjectSelect.innerHTML = '';
                lecturerSubjects.forEach(subject => {
                    const option = document.createElement('option');
                    option.value = subject.code;
                    option.textContent = `${subject.code} - ${subject.name}`;
                    option.selected = subject.code === subjectCode;
                    subjectSelect.appendChild(option);
                });
            }
            
            // Populate student list
            renderStudentAssignmentList();
            
            modal.style.display = 'flex';
        }

        function renderStudentAssignmentList() {
            const container = $('assignmentStudentList');
            if (!container) return;
            
            container.innerHTML = '';
            
            if (filteredStudents.length === 0) {
                container.innerHTML = '<div class="muted">No students available</div>';
                return;
            }
            
            filteredStudents.forEach(student => {
                const div = document.createElement('div');
                div.className = 'student-item';
                div.innerHTML = `
                    <input type="checkbox" id="assign-${student.id}" value="${student.id}">
                    <label for="assign-${student.id}">
                        ${student.first_name} ${student.last_name}
                        <span class="small">(${student.email})</span>
                    </label>
                `;
                container.appendChild(div);
            });
        }

        function renderAssignList(containerId = 'assignUserList', selectedIds = []) {
            const container = $(containerId);
            if (!container) return;
            
            container.innerHTML = '';
            
            if (filteredStudents.length === 0) {
                container.innerHTML = '<div class="muted">No students found</div>';
                return;
            }
            
            filteredStudents.forEach(student => {
                const div = document.createElement('div');
                div.className = 'student-item';
                const isSelected = selectedIds.includes(student.id);
                div.innerHTML = `
                    <input type="checkbox" id="${containerId}-${student.id}" value="${student.id}" ${isSelected ? 'checked' : ''}>
                    <label for="${containerId}-${student.id}">
                        ${student.first_name || student.username} 
                        <span class="small">(${student.email})</span>
                    </label>
                `;
                container.appendChild(div);
            });
        }

        function filterStudents(searchId = 'studentSearch') {
            const searchInput = $(searchId);
            if (!searchInput) return;
            
            const query = searchInput.value.toLowerCase();
            filteredStudents = allStudents.filter(student => {
                const name = `${student.first_name} ${student.last_name}`.toLowerCase();
                const email = (student.email || '').toLowerCase();
                const username = (student.username || '').toLowerCase();
                return name.includes(query) || email.includes(query) || username.includes(query);
            });
            renderAssignList();
        }

      async function createAssignment() {
    const saveBtn = $('saveAssignmentBtn');
    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.textContent = 'Creating...';
    }
    
    if (isCreatingAssignment) {
        showNotification('Assignment creation already in progress', 'warning');
        return;
    }
    
    isCreatingAssignment = true;
    
    try {
        // Enhanced form validation
        const subjectCode = $('assignmentSubject')?.value?.trim();
        const rawName = $('assignmentName')?.value?.trim();
        const description = $('assignmentDescription')?.value?.trim();
        const dueDate = $('assignmentDueDate')?.value;
        const maxPointsInput = $('assignmentMaxPoints')?.value;
        const status = $('assignmentStatus')?.value;
        
        // Comprehensive validation
        if (!subjectCode) {
            throw new Error('Please select a subject');
        }
        
        if (!rawName || rawName.length < 2) {
            throw new Error('Assignment name must be at least 2 characters long');
        }
        
        if (maxPointsInput && (isNaN(maxPointsInput) || parseInt(maxPointsInput) < 0)) {
            throw new Error('Maximum points must be a positive number');
        }
        
        const maxPoints = parseInt(maxPointsInput) || 100;
        
        // Find and validate the subject
        const subject = lecturerSubjects.find(s => s.code === subjectCode);
        if (!subject) {
            throw new Error('Invalid subject selected. Please refresh and try again.');
        }
        
        console.log('Creating assignment with validated data:', {
            name: rawName,
            subject_code: subjectCode,
            lecturer_id: currentUser.id
        });
        
        // Prepare assignment data
        const assignmentData = {
            name: rawName,
            description: description || null,
            due_date: dueDate || null,
            max_points: maxPoints,
            status: status || 'draft',
            subject_code: subject.code,
            student_ids: []
        };
        
        console.log('Sending assignment data to API:', assignmentData);
        
        // Create assignment via API with timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout
        
        const newAssignment = await apiCall('/folders', {
            method: 'POST',
            body: JSON.stringify(assignmentData),
            signal: controller.signal
        });
        
        clearTimeout(timeoutId);
        
        console.log('Assignment created successfully:', newAssignment);
        
        // Update local data structures immediately
        if (newAssignment && newAssignment.id) {
            allFolders.push(newAssignment);
            
            // Auto-expand the subject that contains the new assignment
            expandedFolders.add(`subject_${subject.id}`);
            
            // Immediate UI update with new data
            renderFolderList();
            updateStatistics();
            
            // Show success message
            showNotification(`Assignment "${rawName}" created successfully!`, 'success');
            
            // Close modal and reset form
            closeModal('createAssignmentModal');
            
        } else {
            throw new Error('Invalid response from server - missing assignment ID');
        }
        
    } catch (error) {
        console.error('Error creating assignment:', error);
        
        // Handle different error types
        let errorMessage = 'Failed to create assignment';
        
        if (error.name === 'AbortError') {
            errorMessage = 'Request timed out. Please check your connection and try again.';
        } else if (error.message) {
            errorMessage = error.message;
        }
        
        showNotification(errorMessage, 'error');
        
    } finally {
        isCreatingAssignment = false;
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.textContent = 'Create Assignment';
        }
    }
}
        

        function viewSubmissions(assignmentId) {
            const assignment = allFolders.find(f => f.id === assignmentId);
            if (!assignment) {
                showNotification('Assignment not found', 'error');
                return;
            }
            
            const submissions = allSubmissions.filter(sub => sub.folder_id === assignmentId);
            
            const subViewer = $('subViewer');
            const submissionsContainer = $('submissionsContainer');
            const folderName = $('subViewerFolderName');
            
            if (!subViewer || !submissionsContainer || !folderName) {
                showNotification('Submissions viewer not available', 'error');
                return;
            }
            
            folderName.textContent = assignment.name;
            
            submissionsContainer.innerHTML = '';
            
            if (submissions.length === 0) {
                submissionsContainer.innerHTML = '<div class="muted" style="padding: 20px; text-align: center;">No submissions yet</div>';
            } else {
                submissions.forEach(submission => {
                    const submissionDiv = document.createElement('div');
                    submissionDiv.className = 'folder';
                    submissionDiv.innerHTML = `
                        <div class="left">
                            <div>
                                <div class="name">${submission.first_name} ${submission.last_name}</div>
                                <div class="meta">
                                    Submitted: ${new Date(submission.submitted_at).toLocaleString()}
                                    ${submission.score !== null ? `• Score: ${submission.score}/${assignment.max_points}` : ''}
                                </div>
                            </div>
                            ${submission.status === 'graded' ? '<div class="grade-badge">Graded</div>' : ''}
                        </div>
                        <div class="actions">
                            <button onclick="gradeSubmission(${submission.id})" class="success">
                                ${submission.status === 'graded' ? 'Edit Grade' : 'Grade'}
                            </button>
                        </div>
                    `;
                    submissionsContainer.appendChild(submissionDiv);
                });
            }
            
            subViewer.style.display = 'block';
        }

        // Modal functions
       function closeModal(modalId) {
    const modal = $(modalId);
    if (modal) {
        modal.style.display = 'none';
        
        // If this was the edit modal, reset it
        if (modalId === 'createAssignmentModal' && currentEditingAssignment) {
            closeEditModal();
            return;
        }
        
        // Clear form data for create mode
        const inputs = modal.querySelectorAll('input, textarea, select');
        inputs.forEach(input => {
            if (input.type === 'checkbox') {
                input.checked = false;
            } else {
                input.value = '';
            }
        });
    }
}

// Make functions available globally
window.editAssignment = editAssignment;
window.updateAssignment = updateAssignment;
window.closeEditModal = closeEditModal;
window.deleteAssignment = deleteAssignment;

        function populateCreateAssignmentModal() {
            const subjectSelect = $('assignmentSubject');
            if (!subjectSelect) return;
            
            subjectSelect.innerHTML = '<option value="">Select Subject</option>';
            lecturerSubjects.forEach(subject => {
                const option = document.createElement('option');
                option.value = subject.code;
                option.textContent = `${subject.code} - ${subject.name}`;
                subjectSelect.appendChild(option);
            });
        }

        // Event listeners setup
        function setupEventListeners() {
            // Logout
            const logoutBtn = $('logoutBtn');
            if (logoutBtn) {
                logoutBtn.addEventListener('click', logout);
            }
            
            // Create Assignment Button
            const createAssignmentBtn = $('createAssignmentBtn');
            if (createAssignmentBtn) {
                createAssignmentBtn.addEventListener('click', () => {
                    populateCreateAssignmentModal();
                    renderStudentAssignmentList();
                    const modal = $('createAssignmentModal');
                    if (modal) modal.style.display = 'flex';
                });
            }
            
            // Refresh Subjects Button
            const refreshBtn = $('refreshBtn');
            if (refreshBtn) {
                refreshBtn.addEventListener('click', async () => {
                    refreshBtn.disabled = true;
                    refreshBtn.textContent = 'Refreshing...';
                    try {
                        await loadAllData();
                        showNotification('Data refreshed successfully!');
                    } catch (error) {
                        showNotification('Failed to refresh data', 'error');
                    } finally {
                        refreshBtn.disabled = false;
                        refreshBtn.textContent = 'Refresh Subjects';
                    }
                });
            }
            
            // Show All Submissions Button
            const showAllSubsBtn = $('showAllSubs');
            if (showAllSubsBtn) {
                showAllSubsBtn.addEventListener('click', () => {
                    showNotification('Showing all submissions across all subjects', 'info');
                    // You can implement this functionality to show all submissions
                });
            }
            
            // Modal close buttons
            const cancelAssignmentBtn = $('cancelAssignmentBtn');
            if (cancelAssignmentBtn) {
                cancelAssignmentBtn.addEventListener('click', () => closeModal('createAssignmentModal'));
            }
            
            const saveAssignmentBtn = $('saveAssignmentBtn');
            if (saveAssignmentBtn) {
                saveAssignmentBtn.addEventListener('click', createAssignment);
            }
            
            // Close submissions viewer
            const closeSubs = $('closeSubs');
            if (closeSubs) {
                closeSubs.addEventListener('click', () => {
                    const subViewer = $('subViewer');
                    if (subViewer) subViewer.style.display = 'none';
                });
            }
            
            // Expand/Collapse all buttons
            const expandAllBtn = $('expandAllBtn');
            if (expandAllBtn) {
                expandAllBtn.addEventListener('click', () => {
                    lecturerSubjects.forEach(subject => {
                        expandedFolders.add(`subject_${subject.id}`);
                    });
                    renderFolderList();
                });
            }
            
            const collapseAllBtn = $('collapseAllBtn');
            if (collapseAllBtn) {
                collapseAllBtn.addEventListener('click', () => {
                    expandedFolders.clear();
                    renderFolderList();
                });
            }
            
            // Student search
            const studentSearchInput = $('assignmentStudentSearch');
            if (studentSearchInput) {
                studentSearchInput.addEventListener('input', () => {
                    const query = studentSearchInput.value.toLowerCase();
                    const studentItems = document.querySelectorAll('#assignmentStudentList .student-item');
                    studentItems.forEach(item => {
                        const label = item.querySelector('label');
                        if (label) {
                            const text = label.textContent.toLowerCase();
                            item.style.display = text.includes(query) ? 'flex' : 'none';
                        }
                    });
                });
            }
            
            // Add click handler for modal close buttons (X)
            document.querySelectorAll('.modal .close').forEach(closeBtn => {
                closeBtn.addEventListener('click', (e) => {
                    const modal = e.target.closest('.modal');
                    if (modal) {
                        modal.style.display = 'none';
                    }
                });
            });
        }

        // Global functions for HTML onclick handlers
        window.createAssignmentForSubject = createAssignmentForSubject;
        window.toggleSubjectExpansion = toggleSubjectExpansion;
        window.deleteAssignment = deleteAssignment; // NOW this is defined
        window.editAssignment = editAssignment;
        window.updateAssignment = updateAssignment;
        window.closeEditModal = closeEditModal;
        window.viewSubmissions = viewSubmissions;
        window.gradeSubmission = (id) => showNotification('Grading feature coming soon', 'info');
        window.filterStudents = filterStudents;
        window.closeModal = closeModal;

        window.editSubject = (subjectId) => {
            const subject = lecturerSubjects.find(s => s.id === subjectId);
            if (subject) {
                showNotification(`Edit subject feature for ${subject.code} coming soon`, 'info');
            }
        };

        window.viewSubjectSubmissions = (subjectId) => {
            const subject = lecturerSubjects.find(s => s.id === subjectId);
            if (subject) {
                const subjectAssignments = allFolders.filter(folder => 
                    folder.subject_code === subject.code
                );
                
                const subjectSubmissions = allSubmissions.filter(sub => 
                    subjectAssignments.some(a => a.id === sub.folder_id)
                );
                
                showNotification(`Viewing ${subjectSubmissions.length} submissions for ${subject.code}`, 'info');
            }
        };

        // Close modal when clicking outside
        window.onclick = function(event) {
            const modals = document.getElementsByClassName('modal');
            for (let i = 0; i < modals.length; i++) {
                if (event.target == modals[i]) {
                    modals[i].style.display = 'none';
                }
            }
        };

        // Initialize when DOM is loaded
        document.addEventListener('DOMContentLoaded', async () => {
            console.log('📄 DOM Content Loaded - Lecturer dashboard initializing...');
            
            // Add immediate visual feedback
            const body = document.body;
            if (body) {
                body.style.opacity = '0.5';
                console.log('✅ Body element found, setting loading state');
            }
            
            try {
                // Check authentication first
                console.log('🔐 Step 1: Checking authentication...');
                const isAuthenticated = await checkAuth();
                if (!isAuthenticated) {
                    console.log('❌ Authentication failed, redirecting...');
                    return;
                }
                
                console.log('✅ Authentication successful');
                
                // Update UI with user info
                const lecturerNameEl = $('lecturerName');
                if (lecturerNameEl) {
                    const displayName = currentUser.firstName || currentUser.username || 'Lecturer';
                    lecturerNameEl.textContent = `Hi, ${displayName}`;
                    console.log('✅ Updated lecturer name display');
                }
                
                // Setup event listeners
                console.log('🔧 Step 2: Setting up event listeners...');
                setupEventListeners();
                console.log('✅ Event listeners setup complete');
                
                // Load all data
                console.log('📊 Step 3: Loading dashboard data...');
                await loadAllData();
                console.log('✅ Data loading complete');
                
                console.log('🎉 Lecturer dashboard initialized successfully');
                
            } catch (error) {
                console.error('❌ Error initializing dashboard:', error);
                
                // Show detailed error information
                showNotification(`Dashboard initialization failed: ${error.message}`, 'error');
                
                // Show error state with more details
                if (body) {
                    body.innerHTML = `
                        <div style="padding: 40px; text-align: center; max-width: 600px; margin: 0 auto;">
                            <h2 style="color: #e74c3c; margin-bottom: 20px;">Dashboard Loading Error</h2>
                            <p style="margin-bottom: 20px; color: #666;">
                                There was an error loading the lecturer dashboard. This could be due to:
                            </p>
                            <ul style="text-align: left; margin: 20px 0; color: #666;">
                                <li>Network connectivity issues</li>
                                <li>Server unavailable</li>
                                <li>Authentication problems</li>
                                <li>Database connection issues</li>
                            </ul>
                            <div style="margin: 20px 0;">
                                <strong>Error details:</strong><br>
                                <code style="background: #f8f9fa; padding: 8px; border-radius: 4px; display: inline-block; margin-top: 8px;">
                                    ${error.message}
                                </code>
                            </div>
                            <div style="margin-top: 30px;">
                                <button onclick="location.reload()" style="margin-right: 10px;">Reload Page</button>
                                <button onclick="logout()" class="ghost">Back to Login</button>
                            </div>
                        </div>
                    `;
                }
                
            } finally {
                // Always remove loading state
                if (body) {
                    body.style.opacity = '1';
                }
            }
        });
        // Define deleteAssignment function BEFORE it's referenced
        async function deleteAssignment(assignmentId) {
            console.log('🗑️ Delete assignment called for ID:', assignmentId);
            
            const assignment = allFolders.find(f => f.id === assignmentId);
            if (!assignment) {
                console.error('❌ Assignment not found:', assignmentId);
                showNotification('Assignment not found', 'error');
                return;
            }
            
            const confirmMessage = `Are you sure you want to delete "${assignment.name}"?\n\nThis action cannot be undone and will remove all submissions and student assignments.`;
            
            if (!confirm(confirmMessage)) {
                console.log('🚫 Delete cancelled by user');
                return;
            }
            
            try {
                console.log('🔄 Sending delete request...');
                await apiCall(`/folders/${assignmentId}`, { method: 'DELETE' });
                
                // Remove from local data immediately
                const index = allFolders.findIndex(f => f.id === assignmentId);
                if (index !== -1) {
                    allFolders.splice(index, 1);
                    console.log('✅ Removed from local folders array');
                }
                
                // Remove any related submissions
                const originalSubmissionsCount = allSubmissions.length;
                allSubmissions = allSubmissions.filter(sub => sub.folder_id !== assignmentId);
                console.log(`✅ Removed ${originalSubmissionsCount - allSubmissions.length} related submissions`);
                
                // Update UI immediately
                renderFolderList();
                updateStatistics();
                
                showNotification(`Assignment "${assignment.name}" deleted successfully!`, 'success');
                console.log('✅ Assignment deleted successfully');
                
            } catch (error) {
                console.error('❌ Error deleting assignment:', error);
                showNotification(`Failed to delete assignment: ${error.message}`, 'error');
            }
        }

        // Define editAssignment function
        function editAssignment(assignmentId) {
            console.log('✏️ Edit assignment called for ID:', assignmentId);
            
            const assignment = allFolders.find(f => f.id === assignmentId);
            if (!assignment) {
                console.error('❌ Assignment not found:', assignmentId);
                showNotification('Assignment not found', 'error');
                return;
            }
            
            console.log('✅ Found assignment to edit:', assignment);
            
            try {
                // Set current editing assignment
                currentEditingAssignment = { ...assignment };
                console.log('📝 Set currentEditingAssignment:', currentEditingAssignment);
                
                // Populate the modal with existing data
                populateEditAssignmentModal(assignment);
                
                // Change modal title and button text
                const modalTitle = document.querySelector('#createAssignmentModal .modal-header h2');
                if (modalTitle) {
                    modalTitle.textContent = 'Edit Assignment';
                    console.log('✅ Changed modal title');
                }
                
                const saveBtn = $('saveAssignmentBtn');
                if (saveBtn) {
                    saveBtn.textContent = 'Update Assignment';
                    saveBtn.onclick = null;
                    saveBtn.removeEventListener('click', createAssignment);
                    saveBtn.addEventListener('click', updateAssignment);
                    console.log('✅ Changed button to update mode');
                }
                
                // Show the modal
                const modal = $('createAssignmentModal');
                if (modal) {
                    modal.style.display = 'flex';
                    console.log('✅ Modal displayed');
                }
                
            } catch (error) {
                console.error('❌ Error opening edit modal:', error);
                showNotification('Failed to open edit form: ' + error.message, 'error');
            }
        }

        // Function to populate form with assignment data
        function populateEditAssignmentModal(assignment) {
            console.log('📝 Populating edit form with:', assignment);
            
            try {
                // Populate subject dropdown
                const subjectSelect = $('assignmentSubject');
                if (subjectSelect) {
                    subjectSelect.innerHTML = '';
                    lecturerSubjects.forEach(subject => {
                        const option = document.createElement('option');
                        option.value = subject.code;
                        option.textContent = `${subject.code} - ${subject.name}`;
                        option.selected = subject.code === assignment.subject_code;
                        subjectSelect.appendChild(option);
                    });
                    console.log('✅ Subject dropdown populated');
                }
                
                // Populate form fields with current values
                if ($('assignmentName')) {
                    $('assignmentName').value = assignment.name || '';
                    console.log('✅ Assignment name set');
                }
                
                if ($('assignmentDescription')) {
                    $('assignmentDescription').value = assignment.description || '';
                }
                
                if ($('assignmentMaxPoints')) {
                    $('assignmentMaxPoints').value = assignment.max_points || 100;
                }
                
                if ($('assignmentStatus')) {
                    $('assignmentStatus').value = assignment.status || 'draft';
                }
                
                // Handle due date formatting for datetime-local input
                if ($('assignmentDueDate')) {
                    if (assignment.due_date) {
                        try {
                            const date = new Date(assignment.due_date);
                            if (!isNaN(date.getTime())) {
                                const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
                                $('assignmentDueDate').value = localDate.toISOString().slice(0, 16);
                            }
                        } catch (e) {
                            console.warn('Invalid due date format:', assignment.due_date);
                            $('assignmentDueDate').value = '';
                        }
                    } else {
                        $('assignmentDueDate').value = '';
                    }
                }
                
                // Load and populate current student assignments
                loadAssignmentStudents(assignment.id);
                
                console.log('✅ Edit modal populated successfully');
                
            } catch (error) {
                console.error('❌ Error populating edit modal:', error);
                throw new Error('Failed to load assignment data');
            }
        }

        // Function to load current student assignments
        async function loadAssignmentStudents(assignmentId) {
            try {
                console.log('Loading students for assignment:', assignmentId);
                
                const assignments = await apiCall(`/folders/${assignmentId}/assignments`);
                const assignedStudentIds = assignments
                    .filter(a => a.is_assigned)
                    .map(a => a.id);
                
                console.log('Assigned student IDs:', assignedStudentIds);
                
                // Render student list with current assignments marked
                renderEditStudentList(assignedStudentIds);
                
            } catch (error) {
                console.error('Error loading assignment students:', error);
                showNotification('Failed to load student assignments', 'error');
                
                // Fallback: render all students without assignments marked
                renderEditStudentList([]);
            }
        }

        // New function to render student list for editing
        function renderEditStudentList(assignedStudentIds = []) {
            const container = $('assignmentStudentList');
            if (!container) return;
            
            container.innerHTML = '';
            
            if (allStudents.length === 0) {
                container.innerHTML = '<div class="muted">No students available</div>';
                return;
            }
            
            allStudents.forEach(student => {
                const div = document.createElement('div');
                div.className = 'student-item';
                const isAssigned = assignedStudentIds.includes(student.id);
                
                div.innerHTML = `
                    <input type="checkbox" id="edit-assign-${student.id}" value="${student.id}" ${isAssigned ? 'checked' : ''}>
                    <label for="edit-assign-${student.id}">
                        ${student.first_name} ${student.last_name}
                        <span class="small">(${student.email})</span>
                    </label>
                `;
                container.appendChild(div);
            });
            
            console.log(`Rendered ${allStudents.length} students, ${assignedStudentIds.length} assigned`);
        }

        // Enhanced updateAssignment function
        async function updateAssignment() {
            const saveBtn = $('saveAssignmentBtn');
            if (saveBtn) {
                saveBtn.disabled = true;
                saveBtn.textContent = 'Updating...';
            }
            
            if (isCreatingAssignment) {
                showNotification('Update already in progress', 'warning');
                return;
            }
            
            if (!currentEditingAssignment) {
                showNotification('No assignment selected for editing', 'error');
                return;
            }
            
            isCreatingAssignment = true;
            
            try {
                // Get form values
                const subjectCode = $('assignmentSubject')?.value?.trim();
                const rawName = $('assignmentName')?.value?.trim();
                const description = $('assignmentDescription')?.value?.trim();
                const dueDate = $('assignmentDueDate')?.value;
                const maxPointsInput = $('assignmentMaxPoints')?.value;
                const status = $('assignmentStatus')?.value;
                
                // Enhanced validation
                if (!subjectCode) {
                    throw new Error('Please select a subject');
                }
                
                if (!rawName || rawName.length < 2) {
                    throw new Error('Assignment name must be at least 2 characters long');
                }
                
                if (maxPointsInput && (isNaN(maxPointsInput) || parseInt(maxPointsInput) < 0)) {
                    throw new Error('Maximum points must be a positive number');
                }
                
                const maxPoints = parseInt(maxPointsInput) || 100;
                
                // Validate subject exists
                const subject = lecturerSubjects.find(s => s.code === subjectCode);
                if (!subject) {
                    throw new Error('Invalid subject selected. Please refresh and try again.');
                }
                
                // Collect selected students
                const studentCheckboxes = document.querySelectorAll('#assignmentStudentList input[type="checkbox"]:checked');
                const selectedStudentIds = Array.from(studentCheckboxes).map(cb => parseInt(cb.value));
                
                console.log('Updating assignment with data:', {
                    id: currentEditingAssignment.id,
                    name: rawName,
                    subject_code: subjectCode,
                    student_count: selectedStudentIds.length
                });
                
                // Prepare update data
                const updateData = {
                    name: rawName,
                    description: description || null,
                    due_date: dueDate || null,
                    max_points: maxPoints,
                    status: status,
                    student_ids: selectedStudentIds
                };
                
                console.log('Sending update data to API:', updateData);
                
                // Update assignment via API with timeout
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 15000);
                
                const updatedAssignment = await apiCall(`/folders/${currentEditingAssignment.id}`, {
                    method: 'PUT',
                    body: JSON.stringify(updateData),
                    signal: controller.signal
                });
                
                clearTimeout(timeoutId);
                
                console.log('Assignment updated successfully:', updatedAssignment);
                
                // Update local data structures immediately
                if (updatedAssignment && updatedAssignment.id) {
                    const index = allFolders.findIndex(f => f.id === currentEditingAssignment.id);
                    if (index !== -1) {
                        allFolders[index] = updatedAssignment;
                    }
                    
                    // Auto-expand the subject that contains the updated assignment
                    expandedFolders.add(`subject_${subject.id}`);
                    
                    // Immediate UI update
                    renderFolderList();
                    updateStatistics();
                    
                    // Show success message
                    showNotification(`Assignment "${rawName}" updated successfully!`, 'success');
                    
                    // Close modal and reset
                    closeEditModal();
                    
                } else {
                    throw new Error('Invalid response from server - missing assignment data');
                }
                
            } catch (error) {
                console.error('Error updating assignment:', error);
                
                let errorMessage = 'Failed to update assignment';
                
                if (error.name === 'AbortError') {
                    errorMessage = 'Request timed out. Please check your connection and try again.';
                } else if (error.message) {
                    errorMessage = error.message;
                }
                
                showNotification(errorMessage, 'error');
                
            } finally {
                isCreatingAssignment = false;
                if (saveBtn) {
                    saveBtn.disabled = false;
                    saveBtn.textContent = 'Update Assignment';
                }
            }
        }

        // Define closeEditModal function
        function closeEditModal() {
            currentEditingAssignment = null;
            
            // Reset modal title and button
            const modalTitle = document.querySelector('#createAssignmentModal .modal-header h2');
            if (modalTitle) {
                modalTitle.textContent = 'Create New Assignment';
            }
            
            const saveBtn = $('saveAssignmentBtn');
            if (saveBtn) {
                saveBtn.textContent = 'Create Assignment';
                saveBtn.onclick = null;
                saveBtn.removeEventListener('click', updateAssignment);
                saveBtn.addEventListener('click', createAssignment);
            }
            
            // Close modal and clear form
            closeModal('createAssignmentModal');
            
            console.log('Edit modal closed and reset');
        }

        // Global functions for HTML onclick handlers - NOW THEY'RE DEFINED
        window.createAssignmentForSubject = createAssignmentForSubject;
        window.toggleSubjectExpansion = toggleSubjectExpansion;
        window.deleteAssignment = deleteAssignment; // NOW this is defined
        window.editAssignment = editAssignment;
        window.updateAssignment = updateAssignment;
        window.closeEditModal = closeEditModal;
        window.viewSubmissions = viewSubmissions;
        window.gradeSubmission = (id) => showNotification('Grading feature coming soon', 'info');
        window.filterStudents = filterStudents;
        window.closeModal = closeModal;

        // Initialize when DOM is loaded
        document.addEventListener('DOMContentLoaded', async () => {
            console.log('📄 DOM Content Loaded - Lecturer dashboard initializing...');
            
            // Add immediate visual feedback
            const body = document.body;
            if (body) {
                body.style.opacity = '0.5';
                console.log('✅ Body element found, setting loading state');
            }
            
            try {
                // Check authentication first
                console.log('🔐 Step 1: Checking authentication...');
                const isAuthenticated = await checkAuth();
                if (!isAuthenticated) {
                    console.log('❌ Authentication failed, redirecting...');
                    return;
                }
                
                console.log('✅ Authentication successful');
                
                // Update UI with user info
                const lecturerNameEl = $('lecturerName');
                if (lecturerNameEl) {
                    const displayName = currentUser.firstName || currentUser.username || 'Lecturer';
                    lecturerNameEl.textContent = `Hi, ${displayName}`;
                    console.log('✅ Updated lecturer name display');
                }
                
                // Setup event listeners
                console.log('🔧 Step 2: Setting up event listeners...');
                setupEventListeners();
                console.log('✅ Event listeners setup complete');
                
                // Load all data
                console.log('📊 Step 3: Loading dashboard data...');
                await loadAllData();
                console.log('✅ Data loading complete');
                
                console.log('🎉 Lecturer dashboard initialized successfully');
                
            } catch (error) {
                console.error('❌ Error initializing dashboard:', error);
                
                // Show detailed error information
                showNotification(`Dashboard initialization failed: ${error.message}`, 'error');
                
                // Show error state with more details
                if (body) {
                    body.innerHTML = `
                        <div style="padding: 40px; text-align: center; max-width: 600px; margin: 0 auto;">
                            <h2 style="color: #e74c3c; margin-bottom: 20px;">Dashboard Loading Error</h2>
                            <p style="margin-bottom: 20px; color: #666;">
                                There was an error loading the lecturer dashboard. This could be due to:
                            </p>
                            <ul style="text-align: left; margin: 20px 0; color: #666;">
                                <li>Network connectivity issues</li>
                                <li>Server unavailable</li>
                                <li>Authentication problems</li>
                                <li>Database connection issues</li>
                            </ul>
                            <div style="margin: 20px 0;">
                                <strong>Error details:</strong><br>
                                <code style="background: #f8f9fa; padding: 8px; border-radius: 4px; display: inline-block; margin-top: 8px;">
                                    ${error.message}
                                </code>
                            </div>
                            <div style="margin-top: 30px;">
                                <button onclick="location.reload()" style="margin-right: 10px;">Reload Page</button>
                                <button onclick="logout()" class="ghost">Back to Login</button>
                            </div>
                        </div>
                    `;
                }
                
            } finally {
                // Always remove loading state
                if (body) {
                    body.style.opacity = '1';
                }
            }
        });
