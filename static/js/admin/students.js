// Студенты: список, фильтр, добавление, редактирование, сброс пароля, удаление.
import { escapeHtml } from '../shared/utils.js';
import { authHeaders, formHeaders } from '../shared/api.js';
import { state } from './state.js';
import { loadStats } from './dashboard.js';

function renderStudents(data) {
  document.getElementById('students-tbody').innerHTML = data.length ? data.map(s => `
    <tr>
      <td><code>${escapeHtml(s.student_id)}</code></td>
      <td>${escapeHtml(s.last_name)} ${escapeHtml(s.first_name)}${s.patronymic ? ' ' + escapeHtml(s.patronymic) : ''}</td>
      <td>${escapeHtml(s.group_name || '—')}</td>
      <td>${escapeHtml(s.email || '—')}</td>
      <td class="text-nowrap">
        <button class="btn btn-outline-primary btn-sm" onclick="openEditStudent(${s.id})" title="Редактировать"><i class="bi bi-pencil"></i></button>
        <button class="btn btn-outline-secondary btn-sm" onclick="resetStudentPassword(${s.id})" title="Сбросить пароль"><i class="bi bi-key"></i></button>
        <button class="btn btn-outline-danger btn-sm" onclick="deleteStudent(${s.id})"><i class="bi bi-trash"></i></button>
      </td>
    </tr>`).join('') : '<tr><td colspan="5" class="text-center text-muted">Ничего не найдено</td></tr>';
}

function applyStudentFilter() {
  const q = document.getElementById('student-search').value.toLowerCase().trim();
  const group = document.getElementById('student-group-filter').value;
  renderStudents(state.allStudents.filter(s => {
    const matchQ = !q || s.student_id.toLowerCase().includes(q) ||
      s.last_name.toLowerCase().includes(q) || s.first_name.toLowerCase().includes(q) ||
      (s.patronymic && s.patronymic.toLowerCase().includes(q));
    return matchQ && (!group || s.group_name === group);
  }));
}

export async function loadStudents() {
  const res = await fetch('/api/admin/students', { headers: authHeaders() });
  state.allStudents = await res.json();
  const groups = [...new Set(state.allStudents.map(s => s.group_name).filter(Boolean))].sort();
  const gf = document.getElementById('student-group-filter');
  const prev = gf.value;
  gf.innerHTML = '<option value="">Все группы</option>' + groups.map(g => `<option value="${escapeHtml(g)}">${escapeHtml(g)}</option>`).join('');
  gf.value = prev;
  applyStudentFilter();
}

document.getElementById('student-search').addEventListener('input', applyStudentFilter);
document.getElementById('student-group-filter').addEventListener('change', applyStudentFilter);

document.getElementById('add-student-btn').addEventListener('click', async () => {
  const form = document.getElementById('add-student-form');
  const err = document.getElementById('add-student-error');
  err.classList.add('d-none');
  const body = new URLSearchParams(new FormData(form));
  const res = await fetch('/api/admin/students', { method: 'POST', headers: formHeaders(), body });
  if (res.ok) {
    const data = await res.json();
    bootstrap.Modal.getInstance(document.getElementById('addStudentModal')).hide();
    form.reset();
    document.getElementById('temp-password-value').textContent = data.temp_password;
    document.getElementById('temp-password-alert').classList.remove('d-none');
    loadStudents(); loadStats();
  } else {
    const e = await res.json(); err.textContent = e.detail || 'Ошибка'; err.classList.remove('d-none');
  }
});

let editStudentId = null;
function openEditStudent(id) {
  const s = state.allStudents.find(x => x.id === id);
  if (!s) return;
  editStudentId = id;
  const form = document.getElementById('edit-student-form');
  form.last_name.value = s.last_name;
  form.first_name.value = s.first_name;
  form.patronymic.value = s.patronymic || '';
  form.group_name.value = s.group_name || '';
  form.email.value = s.email || '';
  document.getElementById('edit-student-error').classList.add('d-none');
  new bootstrap.Modal(document.getElementById('editStudentModal')).show();
}

document.getElementById('edit-student-btn').addEventListener('click', async () => {
  const form = document.getElementById('edit-student-form');
  const err = document.getElementById('edit-student-error');
  err.classList.add('d-none');
  const body = new URLSearchParams(new FormData(form));
  const res = await fetch(`/api/admin/students/${editStudentId}`, { method: 'PUT', headers: formHeaders(), body });
  if (res.ok) {
    bootstrap.Modal.getInstance(document.getElementById('editStudentModal')).hide();
    loadStudents();
  } else {
    const e = await res.json(); err.textContent = e.detail || 'Ошибка'; err.classList.remove('d-none');
  }
});

async function resetStudentPassword(id) {
  if (!confirm('Сбросить пароль студента?')) return;
  const res = await fetch(`/api/admin/students/${id}/reset-password`, { method: 'POST', headers: authHeaders() });
  if (res.ok) {
    const data = await res.json();
    document.getElementById('temp-password-value').textContent = data.temp_password;
    document.getElementById('temp-password-alert').classList.remove('d-none');
  }
}

async function deleteStudent(id) {
  if (!confirm('Удалить студента? Все его работы также будут удалены.')) return;
  await fetch(`/api/admin/students/${id}`, { method: 'DELETE', headers: authHeaders() });
  loadStudents(); loadStats();
}

// Вызываются из inline onclick в таблице
window.openEditStudent = openEditStudent;
window.resetStudentPassword = resetStudentPassword;
window.deleteStudent = deleteStudent;
