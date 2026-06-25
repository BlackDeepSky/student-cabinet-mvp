// Задания: список, добавление, редактирование, удаление.
import { escapeHtml } from '../shared/utils.js';
import { authHeaders, formHeaders } from '../shared/api.js';

let allAssignments = [];

export async function loadAssignments() {
  const res = await fetch('/api/admin/assignments', { headers: authHeaders() });
  allAssignments = await res.json();
  document.getElementById('assignments-tbody').innerHTML = allAssignments.map(a => {
    const typeIcon = a.submission_type === 'notebook'
      ? '<span class="badge bg-secondary ms-1" title="В тетради"><i class="bi bi-book"></i></span>'
      : '<span class="badge bg-primary ms-1" title="Электронно"><i class="bi bi-file-earmark-arrow-up"></i></span>';
    return `<tr>
      <td>${escapeHtml(a.subject)}</td>
      <td>${escapeHtml(a.title)} ${typeIcon}</td>
      <td>${escapeHtml(a.deadline || '—')}</td>
      <td class="text-nowrap">
        <button class="btn btn-outline-primary btn-sm" onclick="openEditAssignment(${a.id})" title="Редактировать"><i class="bi bi-pencil"></i></button>
        <button class="btn btn-outline-danger btn-sm" onclick="deleteAssignment(${a.id})"><i class="bi bi-trash"></i></button>
      </td>
    </tr>`;
  }).join('');
}

document.getElementById('open-add-assignment-btn').addEventListener('click', () => {
  new bootstrap.Modal(document.getElementById('addAssignmentModal')).show();
});

document.getElementById('add-assignment-btn').addEventListener('click', async () => {
  const form = document.getElementById('add-assignment-form');
  const err = document.getElementById('add-assignment-error');
  err.classList.add('d-none');
  const body = new URLSearchParams(new FormData(form));
  const res = await fetch('/api/admin/assignments', { method: 'POST', headers: formHeaders(), body });
  if (res.ok) {
    bootstrap.Modal.getInstance(document.getElementById('addAssignmentModal')).hide(); form.reset(); loadAssignments();
  } else {
    const e = await res.json(); err.textContent = e.detail || 'Ошибка'; err.classList.remove('d-none');
  }
});

let editAssignmentId = null;
function openEditAssignment(id) {
  const a = allAssignments.find(x => x.id === id);
  if (!a) return;
  editAssignmentId = id;
  const form = document.getElementById('edit-assignment-form');
  const select = document.getElementById('edit-assignment-subject-select');
  select.innerHTML = document.getElementById('assignment-subject-select').innerHTML;
  select.value = a.subject_id;
  form.title.value = a.title;
  form.description.value = a.description || '';
  form.deadline.value = a.deadline || '';
  const stype = a.submission_type || 'electronic';
  document.getElementById('edit-type-electronic').checked = stype === 'electronic';
  document.getElementById('edit-type-notebook').checked = stype === 'notebook';
  document.getElementById('edit-assignment-error').classList.add('d-none');
  new bootstrap.Modal(document.getElementById('editAssignmentModal')).show();
}

document.getElementById('edit-assignment-btn').addEventListener('click', async () => {
  const form = document.getElementById('edit-assignment-form');
  const err = document.getElementById('edit-assignment-error');
  err.classList.add('d-none');
  const body = new URLSearchParams(new FormData(form));
  const res = await fetch(`/api/admin/assignments/${editAssignmentId}`, { method: 'PUT', headers: formHeaders(), body });
  if (res.ok) {
    bootstrap.Modal.getInstance(document.getElementById('editAssignmentModal')).hide();
    loadAssignments();
  } else {
    const e = await res.json(); err.textContent = e.detail || 'Ошибка'; err.classList.remove('d-none');
  }
});

async function deleteAssignment(id) {
  if (!confirm('Удалить задание?')) return;
  await fetch(`/api/admin/assignments/${id}`, { method: 'DELETE', headers: authHeaders() });
  loadAssignments();
}

// Вызываются из inline onclick в таблице
window.openEditAssignment = openEditAssignment;
window.deleteAssignment = deleteAssignment;
