// lecturer-dashboard.js - LocalStorage-based dashboard code
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

function showNotification(message, type = 'success') {
  const notification = $('notification');
  notification.textContent = message;
  notification.className = `notification ${type} show`;
  setTimeout(() => {
    notification.classList.remove('show');
  }, 3000);
}

const currentUser = JSON.parse(localStorage.getItem(SESSION_KEY) || 'null');
if(!currentUser || currentUser.role !== 'lecturer'){
  alert('Not signed in as lecturer. Redirecting to login.');
  window.location.href = 'Login and Registration.html';
}
$('lecturerName').textContent = `Hi, ${currentUser.firstName || currentUser.username}`;
let allUsers = loadJSON(USERS_KEY);
const students = allUsers.filter(u => u.role === 'student');
filteredStudents = [...students];

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
        content: e.target.result.split(',')[1],
        uploaderId: currentUser ? currentUser.id : null,
        uploadedAt: new Date().toISOString()
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

function getFolders(){ return loadJSON(STORAGE_FOLDERS) }
function saveFolders(f){ saveJSON(STORAGE_FOLDERS,f) }
function getSubs(){ return loadJSON(STORAGE_SUBS) }
function saveSubs(s){ saveJSON(STORAGE_SUBS,s) }

function createFolder(name, assignedTo=[], fileIds=[], description='', dueDate='', maxPoints='', status='active', ownerId = null, parentSubject = null){
  if(!name || !name.toString().trim()) return false;
  const folders = getFolders();
  const resolvedOwnerId = ownerId ?? (currentUser ? currentUser.id : null);
  const resolvedOwnerUsername = (() => {
    if (resolvedOwnerId) {
      const u = allUsers.find(x => x.id === resolvedOwnerId);
      return u ? u.username : (currentUser ? currentUser.username : null);
    }
    return currentUser ? currentUser.username : null;
  })();
  const newFolder = { 
    id: uid('folder'), 
    name: name.toString().trim(), 
    description: description.toString().trim(),
    assignedTo, 
    fileIds,
    dueDate,
    maxPoints: maxPoints ? parseInt(maxPoints) : null,
    status,
    subfolders: [], 
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    ownerId: resolvedOwnerId,
    ownerUsername: resolvedOwnerUsername,
    parentSubject: parentSubject,
    isAssignment: true
  };
  if (parentSubject) {
    const subjectFolder = folders.find(f => f.name === parentSubject && f.isSubject);
    if (subjectFolder) {
      subjectFolder.subfolders.push(newFolder);
      subjectFolder.updatedAt = new Date().toISOString();
    }
  } else {
    folders.push(newFolder);
  }
  saveFolders(folders); 
  showNotification(`Assignment "${name}" created successfully!`);
  renderFolderList();
  updateStatistics();
  return true;
}

function createSubfolder(parentId, name, assignedTo=[], fileIds=[], description='', dueDate='', maxPoints='', status='active'){
  const folders = getFolders();
  const parent = findFolderById(folders, parentId);
  if(!parent) return false;
  const newSubfolder = { 
    id: uid('sub'), 
    name: name.toString().trim(), 
    description: description.toString().trim(),
    assignedTo, 
    fileIds,
    dueDate,
    maxPoints: maxPoints ? parseInt(maxPoints) : null,
    status,
    subfolders: [], 
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    ownerId: parent.ownerId ?? (currentUser ? currentUser.id : null),
    ownerUsername: parent.ownerUsername ?? (currentUser ? currentUser.username : null),
    isAssignment: true
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
  if (updates.assignedTo && folder.subfolders?.length) {
    function updateSubfolders(subfolders) {
      subfolders.forEach(sub => {
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

function getLecturerSubjects() {
  if (!currentUser) return [];
  const subjects = [];
  if (Array.isArray(currentUser.subjects)) {
    subjects.push(...currentUser.subjects);
  }
  if (Array.isArray(currentUser.secondarySubjects)) {
    subjects.push(...currentUser.secondarySubjects);
  }
  return subjects.map(s => (s || '').toString().trim()).filter(Boolean);
}

function folderIsVisibleToLecturer(folder) {
  const subjects = getLecturerSubjects();
  if (!folder) return false;
  if (subjects.includes(folder.name)) return true;
  if (folder.ownerId && currentUser && folder.ownerId === currentUser.id) return true;
  return false;
}

function gatherVisibleFolders(nodes) {
  const result = [];
  nodes.forEach(node => {
    const visibleChildren = node.subfolders && node.subfolders.length ? gatherVisibleFolders(node.subfolders) : [];
    if (folderIsVisibleToLecturer(node)) {
      const copy = Object.assign({}, node, { subfolders: visibleChildren });
      result.push(copy);
    } else {
      visibleChildren.forEach(child => result.push(child));
    }
  });
  return result;
}

function collectAllIds(nodes, set) {
  nodes.forEach(n => {
    set.add(n.id);
    if (n.subfolders && n.subfolders.length) collectAllIds(n.subfolders, set);
  });
}

function getVisibleFolders() {
  const all = getFolders();
  return gatherVisibleFolders(all);
}

function filterStudents(searchId = 'studentSearch') {
  const query = $(searchId).value.toLowerCase();
  filteredStudents = students.filter(student => {
    const name = (student.firstName || student.username).toLowerCase();
    const email = (student.email || '').toLowerCase();
    return name.includes(query) || email.includes(query);
  });
  renderAssignList();
}

function renderAssignList(containerId = 'assignUserList', selectedIds = []){
  const container = $(containerId);
  if (!container) return;
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

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
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
  $('lecturerName').textContent = `Hi, ${currentUser.firstName || currentUser.username}`;
  
  // Load initial data
  loadAllData();
});

// Export functions for HTML onclick handlers
window.deleteSelectedUsers = () => showNotification('Please use the individual folder actions', 'info');
window.resetDatabase = () => showNotification('Database reset is available in the database view', 'info');