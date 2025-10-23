/********************
 * Utilities         *
 ********************/
const $ = (id) => document.getElementById(id);

function fmtDate(iso) {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return '—';
  }
}
function fmtDateShort(iso) {
  try {
    return new Date(iso).toLocaleDateString();
  } catch {
    return '—';
  }
}
function daysUntil(iso) {
  if (!iso) return Infinity;
  const d = (new Date(iso) - new Date()) / (1000 * 60 * 60 * 24);
  return Math.ceil(d);
}

function showNote(msg, type = 'success') {
  const n = $('notification');
  if (!n) return;
  n.textContent = msg;
  n.className = `notification ${type} show`;
  setTimeout(() => n.classList.remove('show'), 3000);
}

/********************
 * Session Guard     *
 ********************/
// const API_BASE = 'http://localhost:8000/api/v1';
const API_BASE = '/api/v1';

function getTokenFromURL() {
  try {
    const u = new URL(window.location.href);
    return u.searchParams.get('token');
  } catch {
    return null;
  }
}

// Also allow reading token from localStorage (same key as lecturer dashboard)
const TOKEN_KEY = 'automark_token';

let token = null;
let currentUser = null;

/********************
 * File Helpers      *
 ********************/
const selectedFiles = new Map(); // Store selected files temporarily

// Convert File objects to base64 payloads (no local storage)
function readFilesAsPayloads(files) {
  return new Promise((resolve) => {
    if (!files || files.length === 0) return resolve([]);
    const out = [];
    let done = 0;
    Array.from(files).forEach((f) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const dataUrl = String(e.target.result || '');
        const base64 = dataUrl.includes(',') ? dataUrl.split(',')[1] : dataUrl;
        out.push({
          name: f.name,
          type: f.type || 'application/octet-stream',
          size: f.size,
          content: base64
        });
        if (++done === files.length) resolve(out);
      };
      reader.readAsDataURL(f);
    });
  });
}

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
window.removeFile = removeFile; // expose for inline onclick

function addFiles(folderId, newFiles) {
  if (!newFiles || newFiles.length === 0) return;
  const existingFiles = selectedFiles.get(folderId) || [];
  const allFiles = [...existingFiles];
  Array.from(newFiles).forEach(file => {
    if (!allFiles.some(existing => existing.name === file.name)) {
      allFiles.push(file);
    }
  });
  selectedFiles.set(folderId, allFiles);
  updateFileList(folderId);
}

// Download file via backend
async function fetchFile(fileId) {
  const res = await fetch(`${API_BASE}/files/${fileId}`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!res.ok) throw new Error('File not found');
  return res.json();
}

async function downloadFile(fileId, fileName) {
  try {
    const f = await fetchFile(fileId);
    const a = document.createElement('a');
    a.href = `data:${f.type};base64,${f.content}`;
    a.download = fileName || f.name || `file_${fileId}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } catch {
    showNote('Failed to download file', 'error');
  }
}
window.downloadFile = downloadFile;

/********************
 * Data Access       *
 ********************/
const expanded = new Set();
let __apiTree = [];
const getFolders = () => __apiTree;

function isActive(folder) {
  const st = (folder.status || '').toLowerCase();
  return st === 'published' || st === 'active';
}

async function fetchCurrentUser() {
  const res = await fetch(`${API_BASE}/auth/session/${token}`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!res.ok) throw new Error('Invalid session');
  const data = await res.json();
  if (!data.valid) throw new Error('Invalid session');
  return data.user;
}

// Fetch assigned folders for the logged-in student
async function fetchAssignedFolders() {
  try {
    const res = await fetch(`${API_BASE}/student/folders`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

// Fetch subjects assigned to the logged-in student
async function fetchStudentSubjects() {
  try {
    const res = await fetch(`${API_BASE}/student/subjects`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

// Fetch my submissions from backend
async function fetchMySubmissions() {
  try {
    const res = await fetch(`${API_BASE}/student/submissions`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

function findById(list, id) {
  for (const f of list) {
    if (String(f.id) === String(id)) return f;
    if (f.subfolders?.length) {
      const x = findById(f.subfolders, id);
      if (x) return x;
    }
  }
  return null;
}

/** Build a Subject -> Assignments tree (subjects are collapsible, assignments are leaf nodes). */
function buildSubjectAssignmentTree(subjects, folders) {
  const grouped = new Map();
  (folders || []).forEach(f => {
    const code = f.subject_code;
    if (!grouped.has(code)) grouped.set(code, []);
    grouped.get(code).push(f);
  });
  if (!subjects || subjects.length === 0) {
    subjects = Array.from(grouped.keys()).map(code => ({ code, name: code, id: code }));
  }
  return (subjects || []).map(s => {
    const children = (grouped.get(s.code) || []).map(f => ({
      id: String(f.id),
      name: f.name,
      description: f.description || '',
      dueDate: f.due_date || null,
      maxPoints: f.max_points || null,
      status: f.status || 'draft',
      fileIds: [], // lecturer materials not modeled server-side yet
      subfolders: [],
      __meAssigned: true
    }));
    return {
      id: `sub_${s.code}`,
      name: `${s.code} - ${s.name}`,
      description: '',
      dueDate: null,
      maxPoints: null,
      status: 'subject',
      fileIds: [],
      subfolders: children,
      __meAssigned: false,
      isSubject: true
    };
  });
}

/********************
 * Rendering         *
 ********************/

async function render() {
  const [subjects, apiFolders, mySubs] = await Promise.all([
    fetchStudentSubjects(),
    fetchAssignedFolders(),
    fetchMySubmissions()
  ]);
  const tree = buildSubjectAssignmentTree(subjects, apiFolders);
  __apiTree = tree;

  const query = ($('searchBox')?.value || '').toLowerCase();
  const main = $('mainList');
  if (!main) return;
  main.innerHTML = '';

  // Auto-expand subjects on first render
  if (expanded.size === 0) {
    tree.forEach(n => {
      if (n.isSubject && n.subfolders && n.subfolders.length) expanded.add(n.id);
    });
  }

  if (tree.length === 0) {
    main.innerHTML = '<div class="small">No active assignments yet. If you were recently enrolled, your lecturer may still be preparing them.</div>';
  }

  let activeCount = 0, submittedCount = 0, dueSoon = 0, graded = 0;

  function renderNode(container, node, level = 0, parentPath = '') {
    const path = parentPath ? parentPath + ' / ' + node.name : node.name;
    const matches = !query || path.toLowerCase().includes(query) || (node.description || '').toLowerCase().includes(query);
    if (!matches) return;

    const hasChildren = (node.subfolders || []).length > 0;
    const open = expanded.has(node.id);
    const icon = hasChildren ? (open ? '📂' : '📁') : '📄';

    // Count only assignment (leaf) nodes
    let existing = null;
    if (!node.isSubject && node.__meAssigned) {
      activeCount++;
      if (daysUntil(node.dueDate) <= 7) dueSoon++;
      existing = mySubs.find(s => String(s.folder_id) === String(node.id));
      if (existing) {
        submittedCount++;
        if (existing.status === 'graded' || existing.score != null) graded++;
      }
    }

    const wrapper = document.createElement('div');
    wrapper.className = 'assignment';
    wrapper.style.paddingLeft = (level * 16) + 'px';

    const due = node.dueDate ? `Due: ${fmtDateShort(node.dueDate)}` : 'No due date';
    const points = node.maxPoints ? `${node.maxPoints} pts` : '—';
    const mat = node.fileIds?.length ? `${node.fileIds.length} file(s)` : 'No materials';

    // Always show Best grade (from latest+best_score API), even if history isn't opened
    const bestGradeHtml = (!node.isSubject && existing && existing.best_score != null)
      ? `<span class="best-grade">Best: ${existing.best_score}</span>`
      : (!node.isSubject ? `<span class="best-grade muted">Best: —</span>` : '');

    const metaHtml = node.isSubject
      ? `<div class="meta"><span class="status subject">Subject</span> • Expand to see assignments</div>`
      : `<div class="meta">
           <span class="status ${isActive(node) ? 'active' : 'draft'}">${isActive(node) ? 'Active' : 'Draft'}</span>
           ${node.__meAssigned ? '<span class="badge">Assigned to you</span>' : ''}
           • ${due} • ${points} • Materials: ${mat} • ${bestGradeHtml}
         </div>`;

    const descHtml = (!node.isSubject && node.description)
      ? `<div class="small" style="margin-top:4px">${node.description}</div>` : '';

    // Existing submission details (files without content)
    const submittedFilesHtml = existing?.files?.length ? `
      <div class="submitted-files">
        <div class="small" style="font-weight: 500; margin-bottom: 4px;">📎 Submitted Files:</div>
        ${existing.files.map(f => `
          <div class="submitted-file">
            <span class="name">${f.name}</span>
            <span class="download" onclick="downloadFile('${f.id}', '${f.name}')">Download</span>
          </div>
        `).join('')}
      </div>
    ` : '';

    const submitHtml = node.isSubject
      ? `<div class="small" style="margin-top:6px;color:#999">Open this subject to view its assignments.</div>`
      : (node.__meAssigned
          ? (hasChildren
              ? '<div class="small" style="margin-top:6px;color:#999">Submissions are only allowed in the <strong>last child folder</strong>. Open a child folder to submit.</div>'
              : renderInlineSubmission(node, existing))
          : '<div class="small" style="margin-top:6px;color:#999">Visible for context (not assigned to you).</div>');

    wrapper.innerHTML = `
      <div class="left">
        <div style="display:flex;gap:8px;align-items:center;cursor:${hasChildren ? 'pointer' : 'default'}" data-toggle="${hasChildren ? node.id : ''}">
          <span style="font-size:12px">${icon}</span>
          <span class="name">${node.name}</span>
        </div>
        ${metaHtml}
        ${descHtml}
        ${submitHtml}
        ${submittedFilesHtml}
      </div>
      <div class="actions">
        ${hasChildren ? `<button class="ghost" data-toggle="${node.id}">${open ? 'Collapse' : 'Expand'}</button>` : ''}
      </div>`;

    container.appendChild(wrapper);

    if (hasChildren && open) {
      const subtree = document.createElement('div');
      subtree.className = 'subtree';
      node.subfolders.forEach(child => renderNode(subtree, child, level + 1, path));
      container.appendChild(subtree);
    }
  }

  tree.forEach(node => renderNode(main, node, 0, ''));

  if ($('statActive')) $('statActive').textContent = activeCount;
  if ($('statSubmitted')) $('statSubmitted').textContent = submittedCount;
  if ($('statDueSoon')) $('statDueSoon').textContent = dueSoon;
  if ($('statGraded')) $('statGraded').textContent = graded;
}

/********************
 * Inline Submission *
 ********************/
function renderInlineSubmission(node, existing) {
  const late = node.dueDate && new Date() > new Date(node.dueDate);
  const gradeLine = (existing && (existing.status === 'graded' || existing.score != null))
    ? `<span class="grade">Grade: ${existing.score ?? '—'}</span>${existing.feedback ? ` • Feedback: ${existing.feedback}` : ''}`
    : '';

  return `
    <form class="inline-form" data-submission-form="${node.id}" onsubmit="return false;">
      ${late ? `<span class="status late" title="Past due">LATE</span>` : ''}
      ${gradeLine}
      
      <!-- Submission History Section -->
      <div class="submission-history" id="history-${node.id}" style="display: none; margin-top: 12px; padding: 12px; background: #f9f9f9; border-radius: 8px;">
        <div style="font-weight: 600; margin-bottom: 8px; cursor: pointer;" onclick="toggleSubmissionHistory('${node.id}')">
          📝 Submission History
        </div>
        <div id="history-items-${node.id}" class="history-items"></div>
      </div>
    </form>
  `;
}

async function toggleSubmissionHistory(folderId) {
  const historyDiv = document.getElementById(`history-${folderId}`);
  if (!historyDiv) return;
  
  if (historyDiv.style.display === 'none') {
    // Load submissions if not already loaded
    const itemsDiv = document.getElementById(`history-items-${folderId}`);
    if (itemsDiv && itemsDiv.innerHTML === '') {
      const submissions = await fetchSVNSubmissions(folderId);
      itemsDiv.innerHTML = renderSubmissionHistory(submissions);
    }
    historyDiv.style.display = 'block';
  } else {
    historyDiv.style.display = 'none';
  }
}

/********************
 * Submission Logic  *
 ********************/
async function handleSubmit(folderId) {
  const folder = findById(getFolders(), folderId);
  if (!folder) { showNote('Assignment not found', 'error'); return; }
 
  if (folder.subfolders && folder.subfolders.length) {
    showNote('You can only submit to the final child folder.', 'error');
    return;
  }
  const selectedFilesForFolder = selectedFiles.get(folderId) || [];
  if (selectedFilesForFolder.length === 0) {
    showNote('Please choose at least one file to upload', 'warning');
    return;
  }

  try {
    const filesPayload = await readFilesAsPayloads(selectedFilesForFolder);
    const res = await fetch(`${API_BASE}/student/submissions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({
        folder_id: Number(folderId),
        files: filesPayload
      })
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => '');
      throw new Error(txt || 'Submission failed');
    }
    selectedFiles.delete(folderId); // clear selected files
    showNote('Submission saved successfully!');
    render();
  } catch (e) {
    showNote('Failed to submit files', 'error');
  }
}

/********************
 * Event Wiring      *
 ********************/
document.addEventListener('DOMContentLoaded', async () => {
  // token = getTokenFromURL();
  token = getTokenFromURL() || localStorage.getItem(TOKEN_KEY);
  if (!token) {
    alert('Not signed in. Redirecting to login.');
    window.location.href = 'login&register.html';
    return;
  }

  try {
    currentUser = await fetchCurrentUser();
  } catch {
    alert('Session invalid or expired. Redirecting to login.');
    window.location.href = 'login&register.html';
    return;
  }

  if (currentUser.role !== 'student') {
    alert('You must be a student to view this page.');
    window.location.href = 'login&register.html';
    return;
  }

  if ($('greeting')) {
    $('greeting').textContent = `Hi, ${currentUser.firstName || currentUser.username || 'Student'}`;
  }

  render();

  const searchBox = $('searchBox');
  if (searchBox) searchBox.addEventListener('input', render);

  document.addEventListener('change', (e) => {
    if (e.target.matches('.file-input')) {
      const folderId = e.target.id.replace('file-', '');
      addFiles(folderId, e.target.files);
      e.target.value = '';
    }
  });

  document.body.addEventListener('click', async (e) => {
    const el = e.target instanceof Element ? e.target : null;
    if (!el) return;

    const toggleEl = el.closest('[data-toggle]');
    if (toggleEl) {
      const tid = toggleEl.getAttribute('data-toggle');
      if (tid) {
        expanded.has(tid) ? expanded.delete(tid) : expanded.add(tid);
        render();
      }
      return;
    }

    const submitEl = el.closest('[data-submit]');
    if (submitEl) {
      e.preventDefault();
      const subFor = submitEl.getAttribute('data-submit');
      if (subFor) await handleSubmit(subFor);
      return;
    }
  });

  const logoutBtn = $('logoutBtn');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', () => {
      // Optionally clear local token if it was used
      try { localStorage.removeItem(TOKEN_KEY); } catch {}
      window.location.href = 'login&register.html';
    });
  }
});

async function fetchSVNSubmissions(folderId) {
  try {
    const res = await fetch(`${API_BASE}/student/svn-submissions/${folderId}`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

function renderSubmissionHistory(submissions) {
  if (!submissions || submissions.length === 0) {
    return '<div class="small" style="color: #999;">No submissions yet</div>';
  }

  return submissions.map(sub => `
    <div class="submission-attempt">
      <span class="attempt-label">Attempt No. ${sub.attempt_number}</span>
      <span class="submission-date">${new Date(sub.submitted_at).toLocaleString()}</span>
      ${sub.status === 'graded' ? `<span class="grade">${sub.score} pts</span>` : ''}
      ${sub.feedback ? `<span class="feedback">${sub.feedback}</span>` : ''}
    </div>
  `).join('');
}