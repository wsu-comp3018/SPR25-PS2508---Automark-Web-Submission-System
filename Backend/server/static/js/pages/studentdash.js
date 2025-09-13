/********************
 * Storage Contracts *
 ********************/
const STORAGE_FOLDERS = 'automark_folders';
const STORAGE_SUBS = 'automark_submissions';
const USERS_KEY = 'automark_users';
const SESSION_KEY = 'automark_user';
const FILES_KEY = 'automark_files';

/********************
 * Utilities         *
 ********************/
const $ = (id) => document.getElementById(id);
const loadJSON = (key, fallback = []) => { try { return JSON.parse(localStorage.getItem(key) || JSON.stringify(fallback)); } catch (e) { return fallback; } };
const saveJSON = (key, obj) => localStorage.setItem(key, JSON.stringify(obj));
const uid = (p = 'id') => p + '_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);

function fmtDate(iso) { try { return new Date(iso).toLocaleString(); } catch { return '—'; } }
function fmtDateShort(iso) { try { return new Date(iso).toLocaleDateString(); } catch { return '—'; } }
function daysUntil(iso) { if (!iso) return Infinity; const d = (new Date(iso) - new Date()) / (1000 * 60 * 60 * 24); return Math.ceil(d); }

function showNote(msg, type = 'success') {
  const n = $('notification');
  n.textContent = msg; n.className = `notification ${type} show`;
  setTimeout(() => n.classList.remove('show'), 3000);
}

/********************
 * Session Guard     *
 ********************/
const currentUser = JSON.parse(localStorage.getItem(SESSION_KEY) || 'null');
if (!currentUser || currentUser.role !== 'student') {
  alert('Not signed in as student. Redirecting to login.');
  window.location.href = 'Login and Registration.html';
}
$('greeting').textContent = `Hi, ${currentUser.firstName || currentUser.username}`;

/********************
 * File Helpers      *
 ********************/
const selectedFiles = new Map(); // Store selected files temporarily

function saveFiles(files) {
  return new Promise((resolve) => {
    const fileIds = [];
    if (!files || files.length === 0) return resolve([]);
    let processed = 0;
    Array.from(files).forEach(f => {
      const reader = new FileReader();
      reader.onload = e => {
        const data = {
          id: uid('file'),
          name: f.name,
          type: f.type,
          size: f.size,
          lastModified: f.lastModified,
          content: String(e.target.result).split(',')[1]
        };
        const all = loadJSON(FILES_KEY, []);
        all.push(data);
        saveJSON(FILES_KEY, all);
        fileIds.push(data.id);
        processed++;
        if (processed === files.length) resolve(fileIds);
      };
      reader.readAsDataURL(f);
    });
  });
}

function getFile(fileId) {
  return loadJSON(FILES_KEY, []).find(f => f.id === fileId);
}

function downloadFile(fileId, fileName) {
  const f = getFile(fileId);
  if (!f) return;
  const a = document.createElement('a');
  a.href = `data:${f.type};base64,${f.content}`;
  a.download = fileName || f.name;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function formatFileSize(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

/********************
 * Data Access       *
 ********************/
const expanded = new Set();
const allUsers = loadJSON(USERS_KEY, []);
const getFolders = () => loadJSON(STORAGE_FOLDERS, []);
const getSubs = () => loadJSON(STORAGE_SUBS, []);
const saveSubs = (s) => saveJSON(STORAGE_SUBS, s);

function isAssignedToMe(folder) { return Array.isArray(folder.assignedTo) && folder.assignedTo.map(String).includes(String(currentUser.id)); }
function isActive(folder) { return (folder.status || 'draft') === 'active'; }

function findById(list, id) {
  for (const f of list) { if (f.id === id) return f; if (f.subfolders?.length) { const x = findById(f.subfolders, id); if (x) return x; } }
  return null;
}

/** Returns all nodes (folders and subfolders) visible to the current student.
 *  A node is visible if: node.status==='active' AND (node.assignedTo includes me).
 *  Parent nodes that are not assigned but have visible children are also shown as context, but are not actionable.
 */
function computeVisibleTree() {
  const roots = getFolders();
  function walk(node) {
    const children = (node.subfolders || []).map(walk).filter(Boolean);
    const meAssigned = isAssignedToMe(node) && isActive(node);
    const hasVisibleChild = children.length > 0;
    if (meAssigned || hasVisibleChild) {
      return { ...node, subfolders: children, __meAssigned: meAssigned };
    }
    return null;
  }
  return roots.map(walk).filter(Boolean);
}

/********************
 * File UI Management *
 ********************/
function updateFileList(folderId) {
  const container = document.querySelector(`[data-file-list="${folderId}"]`);
  if (!container) return;

  const files = selectedFiles.get(folderId) || [];

  if (files.length === 0) {
    container.innerHTML = '<div class="small" style="color: #999; font-style: italic;">No files selected</div>';
    return;
  }

  container.innerHTML = files.map((file, index) => `
    <div class="file-item">
      <span class="file-name">${file.name}</span>
      <span class="file-size">${formatFileSize(file.size)}</span>
      <button class="file-remove" onclick="removeFile('${folderId}', ${index})" title="Remove file">×</button>
    </div>
  `).join('');
}

function removeFile(folderId, index) {
  const files = selectedFiles.get(folderId) || [];
  files.splice(index, 1);
  if (files.length === 0) {
    selectedFiles.delete(folderId);
  } else {
    selectedFiles.set(folderId, files);
  }
  updateFileList(folderId);
}

function addFiles(folderId, newFiles) {
  if (!newFiles || newFiles.length === 0) return;

  const existingFiles = selectedFiles.get(folderId) || [];
  const allFiles = [...existingFiles];

  Array.from(newFiles).forEach(file => {
    // Check for duplicate names
    if (!allFiles.some(existing => existing.name === file.name)) {
      allFiles.push(file);
    }
  });

  selectedFiles.set(folderId, allFiles);
  updateFileList(folderId);
}

/********************
 * Rendering         *
 ********************/
function render() {
  const tree = computeVisibleTree();
  const query = ($('searchBox')?.value || '').toLowerCase();

  const main = $('mainList'); main.innerHTML = '';

  if (tree.length === 0) {
    main.innerHTML = '<div class="small">No active assignments yet. If you were recently enrolled, your lecturer may still be preparing them.</div>';
  }

  let activeCount = 0, submittedCount = 0, dueSoon = 0, graded = 0;
  const mySubs = getSubs().filter(s => s.studentId === String(currentUser.id));

  function renderNode(container, node, level = 0, parentPath = '') {
    const path = parentPath ? parentPath + ' / ' + node.name : node.name;
    const matches = !query || path.toLowerCase().includes(query) || (node.description || '').toLowerCase().includes(query);
    if (!matches) return; // filter

    const hasChildren = (node.subfolders || []).length > 0;
    const open = expanded.has(node.id);
    const icon = hasChildren ? (open ? '📂' : '📁') : '📄';

    // Stats counters
    if (node.__meAssigned) {
      activeCount++;
      if (daysUntil(node.dueDate) <= 7) dueSoon++;
      const sub = mySubs.find(s => s.folderId === node.id);
      if (sub) { submittedCount++; if (sub.graded) graded++; }
    }

    const wrapper = document.createElement('div');
    wrapper.className = 'assignment';
    wrapper.style.paddingLeft = (level * 16) + 'px';

    const due = node.dueDate ? `Due: ${fmtDateShort(node.dueDate)}` : 'No due date';
    const points = node.maxPoints ? `${node.maxPoints} pts` : '—';
    const mat = Array.isArray(node.fileIds) && node.fileIds.length > 0 ? `${node.fileIds.length} file(s)` : 'No materials';

    wrapper.innerHTML = `
      <div class="left">
        <div style="display:flex;gap:8px;align-items:center;cursor:${hasChildren ? 'pointer' : 'default'}" data-toggle="${hasChildren ? node.id : ''}">
          <span style="font-size:12px">${icon}</span>
          <span class="name">${node.name}</span>
        </div>
        <div class="meta">
          <span class="status ${isActive(node) ? 'active' : 'draft'}">${isActive(node) ? 'Active' : 'Draft'}</span>
          ${node.__meAssigned ? '<span class="badge">Assigned to you</span>' : ''}
          • ${due} • ${points} • Materials: ${mat}
        </div>
        ${node.description ? `<div class="small" style="margin-top:4px">${node.description}</div>` : ''}
 
        ${node.fileIds?.length ? `<div class="small" style="margin-top:6px">` + node.fileIds.map(fid => `<a href="#" class="link" data-download-mat="${fid}" title="Download material">${(getFile(fid) || {}).name || 'file'}</a>`).join(' • ') + `</div>` : ''}
 
        ${node.__meAssigned ? (hasChildren ? '<div class="small" style="margin-top:6px;color:#999">Submissions are only allowed in the <strong>last child folder</strong>. Open a child folder to submit.</div>' : renderInlineSubmission(node)) : '<div class="small" style="margin-top:6px;color:#999">Visible for context (not assigned to you).</div>'}
      </div>
      <div class="actions">
        ${hasChildren ? `<button class="ghost" data-toggle="${node.id}">${open ? 'Collapse' : 'Expand'}</button>` : ''}
      </div>`;

    container.appendChild(wrapper);

    // children
    if (hasChildren && open) {
      const subtree = document.createElement('div');
      subtree.className = 'subtree';
      node.subfolders.forEach(child => renderNode(subtree, child, level + 1, path));
      container.appendChild(subtree);
    }
  }

  // Main render only
  tree.forEach(node => { renderNode(main, node, 0, ''); });

  // Stats
  $('statActive').textContent = activeCount;
  $('statSubmitted').textContent = submittedCount;
  $('statDueSoon').textContent = dueSoon;
  $('statGraded').textContent = graded;
}

/********************
 * Inline Submission *
 ********************/
function renderInlineSubmission(node) {
  const allSubs = getSubs();
  const existing = allSubs.find(s => s.folderId === node.id && s.studentId === String(currentUser.id));
  const late = node.dueDate && new Date() > new Date(node.dueDate);
  const gradeLine = existing?.graded ? `<span class="grade">Grade: ${existing.grade ?? '—'}</span>${existing.feedback ? ` • Feedback: ${existing.feedback}` : ''}` : '';

  // Show submitted files
  const submittedFilesHtml = existing?.fileIds?.length ? `
    <div class="submitted-files">
      <div class="small" style="font-weight: 500; margin-bottom: 4px;">📎 Submitted Files:</div>
      ${existing.fileIds.map(fid => {
    const file = getFile(fid);
    return file ? `
          <div class="submitted-file">
            <span class="name">${file.name}</span>
            <span class="download" onclick="downloadFile('${fid}')">Download</span>
          </div>
        ` : '';
  }).join('')}
    </div>
  ` : '';

  return `
    <form class="inline-form" data-submission-form="${node.id}" onsubmit="return false;">
      <input type="file" id="file-${node.id}" class="file-input" multiple accept="*/*" />
      <label class="file-label" for="file-${node.id}">${existing ? 'Add more files…' : 'Choose files…'}</label>
      <button class="${existing ? 'warning' : 'success'}" data-submit="${node.id}">${existing ? 'Update Submission' : 'Submit'}</button>
      ${existing ? `<button class="ghost" data-download-sub="${existing.id}">My Files</button>
                  <button class="ghost danger" data-delete-sub="${existing.id}">Delete</button>` : ''}
     
      <div class="file-list" data-file-list="${node.id}" style="width: 100%; margin-top: 8px;">
        <div class="small" style="color: #999; font-style: italic;">No files selected</div>
      </div>
     
      <span class="hint">${existing ? `Submitted: ${fmtDate(existing.submittedAt)}` : 'No submission yet'}</span>
      ${late ? `<span class="status late" title="Past due">LATE</span>` : ''}
      ${gradeLine}
      ${submittedFilesHtml}
    </form>
  `;
}

/********************
 * Submission Logic  *
 ********************/
async function handleSubmit(folderId) {
  // Guard: must still be assigned and must be a leaf folder
  const folder = findById(getFolders(), folderId);
  if (!folder) { return showNote('Assignment not found', 'error'); }
  if (!isActive(folder) || !isAssignedToMe(folder)) {
    return showNote('You are not allowed to submit to this assignment.', 'error');
  }
  if (folder.subfolders && folder.subfolders.length) {
    return showNote('You can only submit to the final child folder.', 'error');
  }

  // Check for selected files
  const selectedFilesForFolder = selectedFiles.get(folderId) || [];
  if (selectedFilesForFolder.length === 0) {
    return showNote('Please choose at least one file to upload', 'warning');
  }

  const fileIds = await saveFiles(selectedFilesForFolder);
  const subs = getSubs();
  let me = subs.find(s => s.folderId === folderId && s.studentId === String(currentUser.id));

  if (me) {
    // Append files to existing submission
    me.fileIds = (me.fileIds || []).concat(fileIds);
    me.submittedAt = new Date().toISOString();
    me.revisions = (me.revisions || 0) + 1;
  } else {
    me = {
      id: uid('sub'),
      folderId: folderId,
      subfolderId: null,
      studentId: String(currentUser.id),
      submittedAt: new Date().toISOString(),
      fileIds,
      graded: false,
      grade: null,
      feedback: ''
    };
    subs.push(me);
  }

  saveSubs(subs);

  // Clear selected files after successful submission
  selectedFiles.delete(folderId);

  showNote(`Submission saved successfully! ${fileIds.length} file(s) uploaded.`);
  render();
}

function downloadMySubmission(subId) {
  const sub = getSubs().find(s => s.id === subId && s.studentId === String(currentUser.id));
  if (!sub) { return showNote('Submission not found', 'error'); }
  if (!sub.fileIds?.length) { return showNote('No files in this submission', 'warning'); }
  // Download each file individually
  sub.fileIds.forEach(fid => downloadFile(fid));
  showNote(`Downloading ${sub.fileIds.length} file(s)...`);
}

function deleteMySubmission(subId) {
  const subs = getSubs();
  const idx = subs.findIndex(s => s.id === subId && s.studentId === String(currentUser.id));
  if (idx === -1) return showNote('Submission not found', 'error');
  if (!confirm('Delete your submission? This only unlinks the files from this submission.')) return;
  subs.splice(idx, 1); saveSubs(subs); showNote('Submission deleted'); render();
}

/********************
 * Event Wiring      *
 ********************/
document.addEventListener('DOMContentLoaded', () => {
  render();

  // File input handling
  document.addEventListener('change', (e) => {
    if (e.target.matches('.file-input')) {
      const folderId = e.target.id.replace('file-', '');
      addFiles(folderId, e.target.files);
      // Clear the input to allow re-selecting the same files
      e.target.value = '';
    }
  });

  // delegation for expand/collapse + materials download + submission actions
  document.body.addEventListener('click', async (e) => {
    const t = e.target;

    // toggle tree
    const tid = t.getAttribute('data-toggle');
    if (tid) { expanded.has(tid) ? expanded.delete(tid) : expanded.add(tid); render(); }

    // download lecturer material
    const mat = t.getAttribute('data-download-mat');
    if (mat) { e.preventDefault(); downloadFile(mat); }

    // submit/update submission
    const subFor = t.getAttribute('data-submit');
    if (subFor) {
      e.preventDefault();
      await handleSubmit(subFor);
    }

    // download my submission files
    const dsub = t.getAttribute('data-download-sub');
    if (dsub) { e.preventDefault(); downloadMySubmission(dsub); }

    // delete my submission
    const del = t.getAttribute('data-delete-sub');
    if (del) { e.preventDefault(); deleteMySubmission(del); }
  });

  // listen to storage changes (another tab/lecturer updates)
  window.addEventListener('storage', (ev) => {
    if ([STORAGE_FOLDERS, STORAGE_SUBS, FILES_KEY].includes(ev.key)) render();
  });

  // logout
  $('logoutBtn').addEventListener('click', () => {
    localStorage.removeItem('automark_token');
    localStorage.removeItem('automark_user');
    window.location.href = 'Login and Registration.html';
  });

  // diagnostics
  $('runDiagBtn').addEventListener('click', runDiagnostics);
});

/********************
 * Diagnostics       *
 ********************/
function runDiagnostics() {
  const errs = []; const warn = [];
  try {
    if (!currentUser) errs.push('No session user.');
    if (currentUser && currentUser.role !== 'student') errs.push('Session is not a student.');

    const folders = getFolders();
    if (!Array.isArray(folders)) errs.push('Folders storage is not an array.');

    const subs = getSubs();
    if (!Array.isArray(subs)) errs.push('Submissions storage is not an array.');

    // Tree compute should not throw
    computeVisibleTree();

  } catch (e) { errs.push('Exception during diagnostics: ' + (e?.message || e)); }

  if (errs.length) { console.error('[Diagnostics errors]', errs); showNote('Diagnostics: ' + errs.join(' | '), 'error'); }
  else { console.info('[Diagnostics warnings]', warn); showNote('Diagnostics passed. ' + (warn.length ? ('Warnings: ' + warn.join(' | ')) : 'All good.'), 'success'); }
}