
const STORAGE_FOLDERS = 'automark_folders';
const STORAGE_SUBS = 'automark_submissions';
const USERS_KEY = 'automark_users';
const SESSION_KEY = 'automark_user';
const FILES_KEY = 'automark_files';

function $(id){return document.getElementById(id)}
function loadJSON(key){ return JSON.parse(localStorage.getItem(key) || '[]') }
function saveJSON(key, obj){ localStorage.setItem(key, JSON.stringify(obj)) }
function uid(prefix='id'){ return prefix + '_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2,8) }

// Global state
let expandedFolders = new Set();
let filteredStudents = [];

// Notification system
function showNotification(message, type = 'success') {
  const notification = $('notification');
  notification.textContent = message;
  notification.className = `notification ${type} show`;
  setTimeout(() => {
    notification.classList.remove('show');
  }, 3000);
}

// Ensure lecturer
const currentUser = JSON.parse(localStorage.getItem(SESSION_KEY) || 'null');
if(!currentUser || currentUser.role !== 'lecturer'){
  alert('Not signed in as lecturer. Redirecting to login.');
  window.location.href = 'login&register.html';
}
$('lecturerName').textContent = `Hi, ${currentUser.firstName || currentUser.username}`;
let allUsers = loadJSON(USERS_KEY);
const students = allUsers.filter(u => u.role === 'student');
filteredStudents = [...students];

// file handling - multiple files
function saveFiles(files, callback) {
  let savedFiles = [];
  let processed = 0;
  
  if (files.length === 0) {
    callback([]);
    return;
  }
  
  Array.from(files).forEach(file => {
    const reader = new FileReader();
    reader.onload = function(e) {
      const fileData = {
        id: uid('file'),
        name: file.name,
        type: file.type,
        size: file.size,
        lastModified: file.lastModified,
        content: e.target.result.split(',')[1]
      };
      
      const existingFiles = loadJSON(FILES_KEY) || [];
      existingFiles.push(fileData);
      saveJSON(FILES_KEY, existingFiles);
      
      savedFiles.push(fileData.id);
      processed++;
      
      if (processed === files.length) {
        callback(savedFiles);
      }
    };
    reader.readAsDataURL(file);
  });
}

function getFile(fileId) {
  const files = loadJSON(FILES_KEY) || [];
  return files.find(f => f.id === fileId);
}

function downloadFile(fileId, fileName) {
  const file = getFile(fileId);
  if (!file) return;
  
  const link = document.createElement('a');
  link.href = `data:${file.type};base64,${file.content}`;
  link.download = fileName || file.name;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// Enhanced folder functions
function getFolders(){ return loadJSON(STORAGE_FOLDERS) }
function saveFolders(f){ saveJSON(STORAGE_FOLDERS,f) }
function getSubs(){ return loadJSON(STORAGE_SUBS) }
function saveSubs(s){ saveJSON(STORAGE_SUBS,s) }

function createFolder(name, assignedTo=[], fileIds=[], description='', dueDate='', maxPoints='', status='draft'){
  if(!name.trim()) return false;
  const folders = getFolders();
  const newFolder = { 
    id: uid('folder'), 
    name: name.trim(), 
    description: description.trim(),
    assignedTo, 
    fileIds,
    dueDate,
    maxPoints: maxPoints ? parseInt(maxPoints) : null,
    status,
    subfolders: [], 
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  };
  folders.push(newFolder);
  saveFolders(folders); 
  showNotification(`Folder "${name}" created successfully!`);
  renderFolderList();
  updateStatistics();
  return true;
}

function createSubfolder(parentId, name, assignedTo=[], fileIds=[], description='', dueDate='', maxPoints='', status='draft'){
  const folders = getFolders();
  const parent = findFolderById(folders, parentId);
  if(!parent) return false;
  
  const newSubfolder = { 
    id: uid('sub'), 
    name: name.trim(), 
    description: description.trim(),
    assignedTo, 
    fileIds,
    dueDate,
    maxPoints: maxPoints ? parseInt(maxPoints) : null,
    status,
    subfolders: [], 
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  };
  
  parent.subfolders.push(newSubfolder);
  parent.updatedAt = new Date().toISOString();
  saveFolders(folders); 
  showNotification(`Sub-assignment "${name}" created successfully!`);
  renderFolderList();
  updateStatistics();
  return true;
}

function findFolderById(list, id, path = []){
  for(const f of list){
    const currentPath = [...path, f];
    if(f.id === id) return f;
    if(f.subfolders?.length){
      const sub = findFolderById(f.subfolders, id, currentPath);
      if(sub) return sub;
    }
  }
  return null;
}

function removeFolderById(list, id){
  for(let i=0;i<list.length;i++){
    if(list[i].id===id){ 
      list.splice(i,1); 
      return true;
    }
    if(list[i].subfolders?.length){
      if(removeFolderById(list[i].subfolders, id)) {
        list[i].updatedAt = new Date().toISOString();
        return true;
      }
    }
  }
  return false;
}

function updateFolder(folderId, updates) {
  const folders = getFolders();
  const folder = findFolderById(folders, folderId);
  if (!folder) return false;

  Object.assign(folder, updates, { updatedAt: new Date().toISOString() });

  // If updating assignments on parent, optionally cascade to subfolders
  if (updates.assignedTo && folder.subfolders?.length) {
    function updateSubfolders(subfolders) {
      subfolders.forEach(sub => {
        // Only update if subfolder assignments are a subset of parent
        sub.assignedTo = sub.assignedTo.filter(id => updates.assignedTo.includes(id));
        sub.updatedAt = new Date().toISOString();
        if (sub.subfolders?.length) {
          updateSubfolders(sub.subfolders);
        }
      });
    }
    updateSubfolders(folder.subfolders);
  }

  saveFolders(folders);
  return true;
}

// Student search 
function filterStudents() {
  const query = $('studentSearch').value.toLowerCase();
  filteredStudents = students.filter(student => {
    const name = (student.firstName || student.username).toLowerCase();
    const email = (student.email || '').toLowerCase();
    return name.includes(query) || email.includes(query);
  });
  renderAssignList();
}

function renderAssignList(containerId = 'assignUserList', selectedIds = []){
  const container = $(containerId);
  container.innerHTML = '';
  
  if(filteredStudents.length === 0){
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
        ${student.firstName || student.username} 
        <span class="small">(${student.email})</span>
      </label>
    `;
    container.appendChild(div);
  });
}

function renderSubfolderAssignList(parentFolderId){
  const container = $('subfolderAssignList');
  container.innerHTML = '';
  
  const parentFolder = findFolderById(getFolders(), parentFolderId);
  if(!parentFolder || parentFolder.assignedTo.length === 0){
    container.innerHTML = '<div class="muted">No students assigned to parent folder</div>';
    return;
  }
  
  const assignedStudents = students.filter(s => parentFolder.assignedTo.includes(s.id));
  
  assignedStudents.forEach(student => {
    const div = document.createElement('div');
    div.className = 'student-item';
    div.innerHTML = `
      <input type="checkbox" id="sub-assign-${student.id}" value="${student.id}" checked>
      <label for="sub-assign-${student.id}">
        ${student.firstName || student.username} 
        <span class="small">(${student.email})</span>
      </label>
    `;
    container.appendChild(div);
  });
}

function renderEditAssignmentList(folderId) {
  const container = $('editAssignList');
  const folder = findFolderById(getFolders(), folderId);
  if (!folder) {
    container.innerHTML = '<div class="muted">Folder not found</div>';
    return;
  }
  
  $('editFolderName').textContent = folder.name;
  $('editDescription').value = folder.description || '';
  $('editDueDate').value = folder.dueDate || '';
  $('editMaxPoints').value = folder.maxPoints || '';
  $('editStatus').value = folder.status || 'draft';
  $('editAssignmentModal').dataset.folderId = folderId;
  
  renderAssignList('editAssignList', folder.assignedTo);
}

function renderFolderList(){
  const container = $('folderList');
  container.innerHTML = '';
  
  const folders = getFolders();
  if(folders.length === 0){
    container.innerHTML = '<div class="muted">No assignments created yet. Use the form on the left to create your first assignment.</div>';
    return;
  }
  
  folders.forEach(folder => {
    renderFolderItem(container, folder);
  });
}

function renderFolderItem(container, folder, level=0){
  const div = document.createElement('div');
  div.className = `folder ${expandedFolders.has(folder.id) ? 'expanded' : ''}`;
  div.style.paddingLeft = `${level * 16}px`;
  
  const assignedCount = folder.assignedTo?.length || 0;
  const subCount = folder.subfolders?.length || 0;
  const hasFiles = folder.fileIds?.length > 0 ? '📎' : '';
  const statusClass = folder.status === 'active' ? 'active' : 'draft';
  const statusText = folder.status === 'active' ? 'Active' : 'Draft';
  
  // submission count 
  const subs = getSubs();
  const submissionCount = subs.filter(s => s.folderId === folder.id && !s.subfolderId).length;
  
  //  due date
  const dueDateText = folder.dueDate ? 
    `Due: ${new Date(folder.dueDate).toLocaleDateString()}` : 
    'No due date';
  
  const pointsText = folder.maxPoints ? `${folder.maxPoints} pts` : 'No points set';
  
  div.innerHTML = `
    <div class="left">
      <div style="display:flex;align-items:center;gap:8px;cursor:pointer" data-action="toggle" data-id="${folder.id}">
        <span style="font-size:12px">${subCount > 0 ? (expandedFolders.has(folder.id) ? '📂' : '📁') : '📄'}</span>
        <span class="name">${folder.name} ${hasFiles}</span>
      </div>
      <div class="meta">
        <span class="status ${statusClass}">${statusText}</span>
        ${assignedCount} student(s) • ${submissionCount} submission(s) • ${dueDateText} • ${pointsText}
      </div>
      ${folder.description ? `<div class="small" style="margin-top:4px;font-style:italic">${folder.description}</div>` : ''}
    </div>
    <div class="actions">
      ${level < 3 ? `<button class="ghost" data-action="add-sub" data-id="${folder.id}" title="Add Sub-Assignment">+ Sub</button>` : ''}
      <button class="ghost" data-action="edit-assign" data-id="${folder.id}" title="Edit Assignment">Edit</button>
      <button class="ghost" data-action="view-sub" data-id="${folder.id}" title="View Submissions">Submissions</button>
      <button class="ghost" data-action="clone" data-id="${folder.id}" title="Clone Assignment">Clone</button>
      <button class="ghost danger" data-action="delete" data-id="${folder.id}" title="Delete Assignment">Delete</button>
    </div>
  `;
  
  container.appendChild(div);
  
  // Render subfolders if expanded
  if(expandedFolders.has(folder.id) && folder.subfolders?.length > 0){
    const subContainer = document.createElement('div');
    subContainer.className = 'subfolders';
    folder.subfolders.forEach(sub => {
      renderFolderItem(subContainer, sub, level + 1);
    });
    container.appendChild(subContainer);
  }
}

function renderSubmissions(folderId, subfolderId=null){
  const subs = getSubs();
  const container = $('submissionsContainer');
  container.innerHTML = '';
  
  let folder;
  const folders = getFolders();
  folder = findFolderById(folders, subfolderId || folderId);
  
  if(!folder){
    container.innerHTML = '<div class="muted">Folder not found</div>';
    return;
  }
  
  $('subViewerFolderName').textContent = folder.name;
  $('subViewer').style.display = 'block';
  
  const folderSubs = subs.filter(sub => 
    (subfolderId && sub.folderId === folderId && sub.subfolderId === subfolderId) ||
    (!subfolderId && sub.folderId === folderId && !sub.subfolderId)
  );
  
  if(folderSubs.length === 0){
    container.innerHTML = `
      <div class="muted">
        No submissions yet for this ${subfolderId ? 'sub-assignment' : 'assignment'}.
        ${folder.status === 'draft' ? '<br><strong>Note:</strong> This assignment is in draft mode and not visible to students.' : ''}
      </div>
    `;
    return;
  }
  
  // Sort submissions - submission date 
  folderSubs.sort((a, b) => new Date(b.submittedAt) - new Date(a.submittedAt));
  
  folderSubs.forEach(sub => {
    const student = allUsers.find(u => u.id === sub.studentId);
    const isLate = folder.dueDate && new Date(sub.submittedAt) > new Date(folder.dueDate);
    
    const div = document.createElement('div');
    div.className = 'folder';
    div.style.marginBottom = '12px';
    
    // Grade status
    const gradeStatus = sub.graded ? 
      `<span class="grade-badge">Graded: ${sub.grade}/${folder.maxPoints || 'N/A'}</span>` : 
      '<span class="status" style="background:#fff3cd;color:#f39c12">Pending</span>';
    
    div.innerHTML = `
      <div class="left">
        <div style="display:flex;align-items:center;gap:8px">
          <span class="name">${student?.firstName || student?.username || 'Unknown'}</span>
          ${isLate ? '<span class="status" style="background:#ffebee;color:#c62828">LATE</span>' : ''}
          ${gradeStatus}
        </div>
        <div class="meta">
          ${student?.email || 'No email'} • 
          Submitted: ${new Date(sub.submittedAt).toLocaleString()}
          ${sub.fileIds?.length ? ` • ${sub.fileIds.length} file(s)` : ' • No files'}
        </div>
      </div>
      <div class="actions">
        <button class="ghost" data-action="grade" data-id="${sub.id}" title="Grade Submission">Grade</button>
        <a href="#" class="download" data-action="download-sub" data-id="${sub.id}" title="Download Files">Download</a>
        <button class="ghost danger" data-action="delete-sub" data-id="${sub.id}" title="Delete Submission">Delete</button>
      </div>
    `;
    container.appendChild(div);
  });
}

function renderBulkAssignmentLists() {
  const folderContainer = $('bulkFolderList');
  const studentContainer = $('bulkStudentList');
  
  folderContainer.innerHTML = '';
  studentContainer.innerHTML = '';
  
  const folders = getFolders();
  
  function addFolderToList(folder, level = 0) {
    const div = document.createElement('div');
    div.className = 'student-item';
    div.style.paddingLeft = `${level * 16}px`;
    div.innerHTML = `
      <input type="checkbox" id="bulk-folder-${folder.id}" value="${folder.id}">
      <label for="bulk-folder-${folder.id}">
        ${folder.name}
        <span class="small">(${folder.assignedTo.length} students assigned)</span>
      </label>
    `;
    folderContainer.appendChild(div);
    
    if (folder.subfolders?.length) {
      folder.subfolders.forEach(sub => addFolderToList(sub, level + 1));
    }
  }
  
  folders.forEach(folder => addFolderToList(folder));
  
  students.forEach(student => {
    const div = document.createElement('div');
    div.className = 'student-item';
    div.innerHTML = `
      <input type="checkbox" id="bulk-student-${student.id}" value="${student.id}">
      <label for="bulk-student-${student.id}">
        ${student.firstName || student.username} 
        <span class="small">(${student.email})</span>
      </label>
    `;
    studentContainer.appendChild(div);
  });
}

function updateStatistics() {
  const folders = getFolders();
  const submissions = getSubs();
  
  function countFolders(folderList) {
    let count = folderList.length;
    folderList.forEach(folder => {
      if (folder.subfolders?.length) {
        count += countFolders(folder.subfolders);
      }
    });
    return count;
  }
  
  const totalFolders = countFolders(folders);
  const totalStudents = students.length;
  const totalSubmissions = submissions.length;
  const pendingReview = submissions.filter(sub => !sub.graded).length;
  
  $('totalFolders').textContent = totalFolders;
  $('totalStudents').textContent = totalStudents;
  $('totalSubmissions').textContent = totalSubmissions;
  $('pendingReview').textContent = pendingReview;
}

function cloneFolder(originalId) {
  const folders = getFolders();
  const original = findFolderById(folders, originalId);
  if (!original) return false;
  
  const clone = {
    ...original,
    id: uid('folder'),
    name: `${original.name} (Copy)`,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    assignedTo: [], 
    subfolders: cloneSubfolders(original.subfolders || [])
  };
  
  folders.push(clone);
  saveFolders(folders);
  showNotification(`Assignment "${original.name}" cloned successfully!`);
  renderFolderList();
  updateStatistics();
  return true;
}

function cloneSubfolders(subfolders) {
  return subfolders.map(sub => ({
    ...sub,
    id: uid('sub'),
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    assignedTo: [],
    subfolders: cloneSubfolders(sub.subfolders || [])
  }));
}

// Grading functions
function openGradingModal(submissionId) {
  const subs = getSubs();
  const submission = subs.find(s => s.id === submissionId);
  if (!submission) return;
  
  const student = allUsers.find(u => u.id === submission.studentId);
  const folder = findFolderById(getFolders(), submission.folderId);
  const subfolder = submission.subfolderId ? 
    findFolderById(getFolders(), submission.subfolderId) : null;
  
  // Populate modal with data
  $('gradingStudentName').textContent = student?.firstName || student?.username || 'Unknown';
  $('gradingAssignmentName').textContent = subfolder ? 
    `${folder.name} → ${subfolder.name}` : folder.name;
  
  // Set max score
  const maxPoints = subfolder ? subfolder.maxPoints : folder.maxPoints;
  $('maxScore').textContent = maxPoints || '100';
  $('submissionScore').max = maxPoints || 100;
  
  // Set current grade if exists
  $('submissionScore').value = submission.grade || '';
  $('submissionFeedback').value = submission.feedback || '';
  
  // Show submitted files
  const fileList = $('gradingFileList');
  fileList.innerHTML = '';
  
  if (submission.fileIds && submission.fileIds.length > 0) {
    submission.fileIds.forEach(fileId => {
      const file = getFile(fileId);
      if (file) {
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';
        fileItem.innerHTML = `
          <span class="file-name">${file.name}</span>
          <a href="#" class="download" onclick="downloadFile('${fileId}', '${file.name}'); return false;">Download</a>
        `;
        fileList.appendChild(fileItem);
      }
    });
  } else {
    fileList.innerHTML = '<div class="muted">No files submitted</div>';
  }
  
  // Store submission ID in modal dataset
  $('gradingModal').dataset.submissionId = submissionId;
  $('gradingModal').style.display = 'flex';
}

function saveGrade() {
  const submissionId = $('gradingModal').dataset.submissionId;
  const score = parseInt($('submissionScore').value);
  const feedback = $('submissionFeedback').value.trim();
  
  if (isNaN(score)) {
    showNotification('Please enter a valid score', 'error');
    return;
  }
  
  const subs = getSubs();
  const submissionIndex = subs.findIndex(s => s.id === submissionId);
  
  if (submissionIndex === -1) {
    showNotification('Submission not found', 'error');
    return;
  }
  
  // Update submission with grade and feedback
  subs[submissionIndex].grade = score;
  subs[submissionIndex].feedback = feedback;
  subs[submissionIndex].graded = true;
  subs[submissionIndex].gradedAt = new Date().toISOString();
  
  saveSubs(subs);
  showNotification('Grade saved successfully!');
  $('gradingModal').style.display = 'none';
  
  // Refresh the view if we're in submissions view
  if ($('subViewer').style.display !== 'none') {
    const folderName = $('subViewerFolderName').textContent;
    const folders = getFolders();
    const folder = folders.find(f => f.name === folderName);
    if(folder) renderSubmissions(folder.id);
  }
}

// Format filename for download
function formatDownloadFileName(fileId, submission, student) {
  const file = getFile(fileId);
  if (!file) return 'file';
  
  const baseName = file.name.replace(/\.[^/.]+$/, "");
  const extension = file.name.includes('.') ? file.name.split('.').pop() : '';
  
  // Format timestamp for filename (remove special characters)
  const timestamp = new Date(submission.submittedAt).toISOString()
    .replace(/[:.]/g, '-')
    .replace('T', '_')
    .substring(0, 19);
  
  // Get grade if exists
  const grade = submission.graded ? `_${submission.grade}` : '_ungraded';
  
  return `${baseName}_${student.username}_${timestamp}${grade}.${extension}`;
}

// Event listeners
document.addEventListener('DOMContentLoaded', () => {
  // File input handlers with multiple file support
  $('folderFile').addEventListener('change', (e) => {
    const files = e.target.files;
    if(files.length > 0){
      const names = Array.from(files).map(f => f.name).join(', ');
      const totalSize = Array.from(files).reduce((sum, f) => sum + f.size, 0);
      $('folderFileInfo').textContent = `${files.length} file(s): ${names} (${(totalSize/1024).toFixed(1)} KB total)`;
    } else {
      $('folderFileInfo').textContent = 'No files selected';
    }
  });
  
  $('subfolderFile').addEventListener('change', (e) => {
    const files = e.target.files;
    if(files.length > 0){
      const names = Array.from(files).map(f => f.name).join(', ');
      const totalSize = Array.from(files).reduce((sum, f) => sum + f.size, 0);
      $('subfolderFileInfo').textContent = `${files.length} file(s): ${names} (${(totalSize/1024).toFixed(1)} KB total)`;
    } else {
      $('subfolderFileInfo').textContent = 'No files selected';
    }
  });
  
  // Student search
  $('studentSearch').addEventListener('input', filterStudents);
  
  // Create main folder
  $('createFolderBtn').addEventListener('click', () => {
    const name = $('newFolderName').value.trim();
    const description = $('folderDescription').value.trim();
    const dueDate = $('folderDueDate').value;
    const maxPoints = $('folderMaxPoints').value;
    const status = $('folderStatus').value;
    
    if(!name) return showNotification('Please enter a folder name', 'error');
    
    const checked = Array.from($('assignUserList').querySelectorAll('input:checked'));
    const assignedTo = checked.map(el => el.value);
    
    const fileInput = $('folderFile');
    if(fileInput.files.length > 0){
      saveFiles(fileInput.files, (fileIds) => {
        if(createFolder(name, assignedTo, fileIds, description, dueDate, maxPoints, status)){
          clearFolderForm();
        }
      });
    } else {
      if(createFolder(name, assignedTo, [], description, dueDate, maxPoints, status)){
        clearFolderForm();
      }
    }
  });
  
  function clearFolderForm() {
    $('newFolderName').value = '';
    $('folderDescription').value = '';
    $('folderDueDate').value = '';
    $('folderMaxPoints').value = '';
    $('folderStatus').value = 'draft';
    $('folderFile').value = '';
    $('folderFileInfo').textContent = 'No files selected';
    $('assignUserList').querySelectorAll('input').forEach(el => el.checked = false);
    $('studentSearch').value = '';
    filterStudents();
  }
  
  // Reset form
  $('resetFoldersBtn').addEventListener('click', clearFolderForm);
  
  // Expand/Collapse 
  $('expandAllBtn').addEventListener('click', () => {
    const folders = getFolders();
    function addAllIds(folderList) {
      folderList.forEach(folder => {
        expandedFolders.add(folder.id);
        if (folder.subfolders?.length) {
          addAllIds(folder.subfolders);
        }
      });
    }
    addAllIds(folders);
    renderFolderList();
  });
  
  $('collapseAllBtn').addEventListener('click', () => {
    expandedFolders.clear();
    renderFolderList();
  });
  
  // Folder list actions
  $('folderList').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action]');
    if(!btn) return;
    
    const action = btn.dataset.action;
    const id = btn.dataset.id;
    
    if(action === 'toggle'){
      if(expandedFolders.has(id)){
        expandedFolders.delete(id);
      } else {
        expandedFolders.add(id);
      }
      renderFolderList();
    }
    else if(action === 'add-sub'){
      const folder = findFolderById(getFolders(), id);
      if(!folder) return;
      
      $('subfolderModal').style.display = 'flex';
      $('newSubfolderName').value = '';
      $('subfolderDescription').value = '';
      $('subfolderDueDate').value = '';
      $('subfolderMaxPoints').value = '';
      $('subfolderStatus').value = 'draft';
      $('subfolderFile').value = '';
      $('subfolderFileInfo').textContent = 'No files selected';
      $('subfolderModal').dataset.parentId = id;
      renderSubfolderAssignList(id);
    }
    else if(action === 'edit-assign'){
      renderEditAssignmentList(id);
      $('editAssignmentModal').style.display = 'flex';
    }
    else if(action === 'view-sub'){
      renderSubmissions(id);
    }
    else if(action === 'clone'){
      if(confirm('Clone this assignment? The clone will have no students assigned.')) {
        cloneFolder(id);
      }
    }
    else if(action === 'delete'){
      if(!confirm('Delete this assignment and all its contents? This cannot be undone.')) return;
      const folders = getFolders();
      if(removeFolderById(folders, id)){
        saveFolders(folders);
        showNotification('Assignment deleted successfully');
        renderFolderList();
        updateStatistics();
      }
    }
  });
  
  // Submissions container actions
  $('submissionsContainer').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action]');
    if(!btn) return;
    
    const action = btn.dataset.action;
    const id = btn.dataset.id;
    
    if(action === 'download-sub'){
      e.preventDefault();
      const sub = getSubs().find(s => s.id === id);
      if(sub && sub.fileIds?.length > 0){
        const student = allUsers.find(u => u.id === sub.studentId);
        sub.fileIds.forEach((fileId, index) => {
          const fileName = formatDownloadFileName(fileId, sub, student);
          setTimeout(() => {
            downloadFile(fileId, fileName);
          }, index * 100); 
        });
        showNotification(`Downloading ${sub.fileIds.length} file(s)...`);
      } else {
        showNotification('No files to download', 'warning');
      }
    }
    else if(action === 'grade'){
      openGradingModal(id);
    }
    else if(action === 'delete-sub'){
      if(!confirm('Delete this submission? This cannot be undone.')) return;
      const subs = getSubs();
      const idx = subs.findIndex(x => x.id === id);
      if(idx > -1) {
        subs.splice(idx, 1);
        saveSubs(subs);
        showNotification('Submission deleted');
        
        // Refresh the current view
        const folderName = $('subViewerFolderName').textContent;
        const folders = getFolders();
        const folder = folders.find(f => f.name === folderName);
        if(folder) renderSubmissions(folder.id);
        updateStatistics();
      }
    }
  });
  
  // Download submissions
  $('downloadAllSubs').addEventListener('click', () => {
    const folderName = $('subViewerFolderName').textContent;
    const subs = getSubs();
    const folderSubs = subs.filter(sub => {
      const folder = findFolderById(getFolders(), sub.folderId);
      return folder && folder.name === folderName;
    });
    
    if(folderSubs.length === 0) {
      showNotification('No submissions to download', 'warning');
      return;
    }
    
    let downloadCount = 0;
    folderSubs.forEach((sub, subIndex) => {
      if(sub.fileIds?.length > 0) {
        const student = allUsers.find(u => u.id === sub.studentId);
        sub.fileIds.forEach((fileId, fileIndex) => {
          const fileName = formatDownloadFileName(fileId, sub, student);
          setTimeout(() => {
            downloadFile(fileId, fileName);
          }, downloadCount * 200);
          downloadCount++;
        });
      }
    });
    
    if(downloadCount > 0) {
      showNotification(`Downloading ${downloadCount} file(s) from ${folderSubs.length} submission(s)...`);
    } else {
      showNotification('No files found in submissions', 'warning');
    }
  });
  
  // Grading actions
  $('cancelGradingBtn').addEventListener('click', () => {
    $('gradingModal').style.display = 'none';
  });
  
  $('saveGradingBtn').addEventListener('click', saveGrade);
  
  // Subfolder actions
  $('cancelSubfolderBtn').addEventListener('click', () => {
    $('subfolderModal').style.display = 'none';
  });
  
  $('createSubfolderBtn').addEventListener('click', () => {
    const parentId = $('subfolderModal').dataset.parentId;
    const name = $('newSubfolderName').value.trim();
    const description = $('subfolderDescription').value.trim();
    const dueDate = $('subfolderDueDate').value;
    const maxPoints = $('subfolderMaxPoints').value;
    const status = $('subfolderStatus').value;
    
    if(!name) return showNotification('Please enter a sub-assignment name', 'error');
    
    const checked = Array.from($('subfolderAssignList').querySelectorAll('input:checked'));
    const assignedTo = checked.map(el => el.value);
    
    const fileInput = $('subfolderFile');
    if(fileInput.files.length > 0){
      saveFiles(fileInput.files, (fileIds) => {
        if(createSubfolder(parentId, name, assignedTo, fileIds, description, dueDate, maxPoints, status)){
          $('subfolderModal').style.display = 'none';
          expandedFolders.add(parentId); 
        }
      });
    } else {
      if(createSubfolder(parentId, name, assignedTo, [], description, dueDate, maxPoints, status)){
        $('subfolderModal').style.display = 'none';
        expandedFolders.add(parentId);
      }
    }
  });
  
  // Edit assignment actions
  $('cancelEditAssignmentBtn').addEventListener('click', () => {
    $('editAssignmentModal').style.display = 'none';
  });
  
  $('saveAssignmentBtn').addEventListener('click', () => {
    const folderId = $('editAssignmentModal').dataset.folderId;
    const checked = Array.from($('editAssignList').querySelectorAll('input:checked'));
    const assignedTo = checked.map(el => el.value);
    
    const updates = {
      assignedTo,
      description: $('editDescription').value.trim(),
      dueDate: $('editDueDate').value,
      maxPoints: $('editMaxPoints').value ? parseInt($('editMaxPoints').value) : null,
      status: $('editStatus').value
    };
    
    if(updateFolder(folderId, updates)) {
      showNotification('Assignment updated successfully!');
      $('editAssignmentModal').style.display = 'none';
      renderFolderList();
      updateStatistics();
    } else {
      showNotification('Failed to update assignment', 'error');
    }
  });
  
  // Close submissions view
  $('closeSubs').addEventListener('click', () => {
    $('subViewer').style.display = 'none';
  });
  
  // Show all submissions
  $('showAllSubs').addEventListener('click', () => {
    const subs = getSubs();
    const container = $('submissionsContainer');
    container.innerHTML = '';
    
    $('subViewerFolderName').textContent = 'All Submissions';
    $('subViewer').style.display = 'block';
    
    if(subs.length === 0){
      container.innerHTML = '<div class="muted">No submissions found across all assignments.</div>';
      return;
    }
    
    // Sort by submission date
    subs.sort((a, b) => new Date(b.submittedAt) - new Date(a.submittedAt));
    
    subs.forEach(sub => {
      const student = allUsers.find(u => u.id === sub.studentId);
      const folder = findFolderById(getFolders(), sub.folderId);
      const subfolder = sub.subfolderId ? findFolderById(getFolders(), sub.subfolderId) : null;
      
      const div = document.createElement('div');
      div.className = 'folder';
      div.style.marginBottom = '12px';
      div.innerHTML = `
        <div class="left">
          <div style="display:flex;align-items:center;gap:8px">
            <span class="name">${student?.firstName || student?.username || 'Unknown'}</span>
          </div>
          <div class="meta">
            Submitted to: ${folder?.name || 'Unknown'}${subfolder ? ` → ${subfolder.name}` : ''} • 
            ${new Date(sub.submittedAt).toLocaleString()}
            ${sub.fileIds?.length ? ` • ${sub.fileIds.length} file(s)` : ' • No files'}
          </div>
        </div>
        <div class="actions">
          <button class="ghost" data-action="grade" data-id="${sub.id}">Grade</button>
          <a href="#" class="download" data-action="download-sub" data-id="${sub.id}">Download</a>
          <button class="ghost danger" data-action="delete-sub" data-id="${sub.id}">Delete</button>
        </div>
      `;
      container.appendChild(div);
    });
  });
  
  // Bulk assigning students
  $('bulkAssign').addEventListener('click', () => {
    renderBulkAssignmentLists();
    $('bulkAssignModal').style.display = 'flex';
  });
  
  $('selectAllStudents').addEventListener('click', () => {
    $('bulkStudentList').querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = true);
  });
  
  $('deselectAllStudents').addEventListener('click', () => {
    $('bulkStudentList').querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = false);
  });
  
  $('cancelBulkAssignBtn').addEventListener('click', () => {
    $('bulkAssignModal').style.display = 'none';
  });
  
  $('applyBulkAssignBtn').addEventListener('click', () => {
    const selectedFolders = Array.from($('bulkFolderList').querySelectorAll('input:checked')).map(el => el.value);
    const selectedStudents = Array.from($('bulkStudentList').querySelectorAll('input:checked')).map(el => el.value);
    
    if(selectedFolders.length === 0 || selectedStudents.length === 0) {
      showNotification('Please select both folders and students', 'error');
      return;
    }
    
    let updated = 0;
    selectedFolders.forEach(folderId => {
      if(updateFolder(folderId, { assignedTo: selectedStudents })) {
        updated++;
      }
    });
    
    if(updated > 0) {
      showNotification(`Updated ${updated} assignment(s) successfully!`);
      $('bulkAssignModal').style.display = 'none';
      renderFolderList();
      updateStatistics();
    } else {
      showNotification('Failed to update assignments', 'error');
    }
  });
  
  // Exporting data
  $('exportData').addEventListener('click', () => {
    const data = {
      folders: getFolders(),
      submissions: getSubs(),
      users: allUsers.filter(u => u.role === 'student'), 
      files: loadJSON(FILES_KEY) || [],
      exportedAt: new Date().toISOString(),
      version: '2.0'
    };
    
    const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `automark-export-${new Date().toISOString().slice(0,10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showNotification('Data exported successfully!');
  });
  
  // Logout
  $('logoutBtn').addEventListener('click', () => {
    if(confirm('Are you sure you want to sign out?')) {
      localStorage.removeItem(SESSION_KEY);
      location.href = 'login&register.html';
    }
  });
  
  // start actions
  filterStudents();
  renderFolderList();
  updateStatistics();
});
