// Прогресс студентов по предметам.
import { escapeHtml, showToast } from '../shared/utils.js';
import { getAuthHeaders, logoutToLogin } from './api.js';

async function loadProgress(subjectId) {
  const url = subjectId ? `/api/teacher/progress?subject_id=${subjectId}` : '/api/teacher/progress';
  const res = await fetch(url, { headers: getAuthHeaders() });
  if (res.status === 401 || res.status === 403) { logoutToLogin(); return; }
  if (!res.ok) { showToast('Ошибка загрузки прогресса', 'danger'); return; }
  const data = await res.json();
  const filter = document.getElementById('progress-subject-filter');
  if (filter.options.length === 1) {
    data.subjects.forEach(s => {
      const opt = document.createElement('option'); opt.value = s.id; opt.textContent = s.name; filter.appendChild(opt);
    });
  }
  renderProgress(data.rows);
}

function renderProgress(rows) {
  const tbody = document.getElementById('progress-rows');
  const emptyMsg = document.getElementById('progress-empty');
  tbody.innerHTML = '';
  if (rows.length === 0) { emptyMsg.style.display = 'block'; return; }
  emptyMsg.style.display = 'none';
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const STATUS_LABELS = { submitted: 'Отправлено', in_review: 'На рассмотрении', approved: 'Зачтено', rejected: 'Не зачтено', resubmitted: 'Повторно отправлено', notebook_sent: 'Тетрадь отправлена почтой' };
  rows.forEach(row => {
    const isApproved = row.status === 'approved';
    const isNotSubmitted = !row.status;
    const isRejected = row.status === 'rejected';
    const deadline = row.deadline ? new Date(row.deadline) : null;
    const isOverdue = deadline && deadline < today && !isApproved;
    let rowClass = '';
    if (isApproved) rowClass = 'table-success';
    else if (isOverdue && isNotSubmitted) rowClass = 'table-danger';
    else if (isNotSubmitted || isRejected) rowClass = 'table-warning';
    const deadlineStr = deadline ? deadline.toLocaleDateString('ru-RU') + (isOverdue ? ' ⚠️' : '') : '—';
    const statusLabel = row.status ? STATUS_LABELS[row.status] || row.status : 'Не сдано';
    const submittedAt = row.submitted_at ? new Date(row.submitted_at).toLocaleDateString('ru-RU') : '—';
    const tr = document.createElement('tr');
    if (rowClass) tr.className = rowClass;
    tr.innerHTML = `
      <td>${escapeHtml(row.student_name)}<br><small class="text-muted">${escapeHtml(row.student_id)}</small></td>
      <td>${escapeHtml(row.subject)}</td>
      <td>${escapeHtml(row.assignment_title)}</td>
      <td>${deadlineStr}</td>
      <td>${escapeHtml(statusLabel)}</td>
      <td>${submittedAt}</td>`;
    tbody.appendChild(tr);
  });
}

document.getElementById('show-progress-btn').addEventListener('click', () => {
  bootstrap.Modal.getOrCreateInstance(document.getElementById('progressModal')).show();
  loadProgress('');
});
document.getElementById('progress-subject-filter').addEventListener('change', e => loadProgress(e.target.value));
