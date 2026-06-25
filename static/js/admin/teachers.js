// Преподаватели: список, фильтр, добавление, редактирование, сброс пароля, удаление.
import { escapeHtml } from '../shared/utils.js';
import { authHeaders, formHeaders } from '../shared/api.js';
import { state } from './state.js';
import { loadStats } from './dashboard.js';

function renderTeachers(data) {
  document.getElementById('teachers-tbody').innerHTML = data.length ? data.map(t => `
    <tr>
      <td><code>${escapeHtml(t.teacher_id)}</code></td>
      <td>${escapeHtml(t.last_name)} ${escapeHtml(t.first_name)}${t.patronymic ? ' ' + escapeHtml(t.patronymic) : ''}</td>
      <td>${escapeHtml(t.email || '—')}</td>
      <td class="text-nowrap">
        <button class="btn btn-outline-primary btn-sm" onclick="openEditTeacher(${t.id})" title="Редактировать"><i class="bi bi-pencil"></i></button>
        <button class="btn btn-outline-secondary btn-sm" onclick="resetTeacherPassword(${t.id})" title="Сбросить пароль"><i class="bi bi-key"></i></button>
        <button class="btn btn-outline-danger btn-sm" onclick="deleteTeacher(${t.id})"><i class="bi bi-trash"></i></button>
      </td>
    </tr>`).join('') : '<tr><td colspan="4" class="text-center text-muted">Ничего не найдено</td></tr>';
}

function applyTeacherFilter() {
  const q = document.getElementById('teacher-search').value.toLowerCase().trim();
  renderTeachers(state.allTeachers.filter(t => !q ||
    t.teacher_id.toLowerCase().includes(q) || t.last_name.toLowerCase().includes(q) ||
    t.first_name.toLowerCase().includes(q) || (t.patronymic && t.patronymic.toLowerCase().includes(q))));
}

export async function loadTeachers() {
  const res = await fetch('/api/admin/teachers', { headers: authHeaders() });
  state.allTeachers = await res.json();
  applyTeacherFilter();
}

document.getElementById('teacher-search').addEventListener('input', applyTeacherFilter);

document.getElementById('add-teacher-btn').addEventListener('click', async () => {
  const form = document.getElementById('add-teacher-form');
  const err = document.getElementById('add-teacher-error');
  err.classList.add('d-none');
  const body = new URLSearchParams(new FormData(form));
  const res = await fetch('/api/admin/teachers', { method: 'POST', headers: formHeaders(), body });
  if (res.ok) {
    const data = await res.json();
    bootstrap.Modal.getInstance(document.getElementById('addTeacherModal')).hide();
    form.reset();
    document.getElementById('temp-teacher-password-value').textContent = data.temp_password;
    document.getElementById('temp-teacher-password-alert').classList.remove('d-none');
    loadTeachers(); loadStats();
  } else {
    const e = await res.json(); err.textContent = e.detail || 'Ошибка'; err.classList.remove('d-none');
  }
});

let editTeacherId = null;
function openEditTeacher(id) {
  const t = state.allTeachers.find(x => x.id === id);
  if (!t) return;
  editTeacherId = id;
  const form = document.getElementById('edit-teacher-form');
  form.last_name.value = t.last_name;
  form.first_name.value = t.first_name;
  form.patronymic.value = t.patronymic || '';
  form.email.value = t.email || '';
  document.getElementById('edit-teacher-error').classList.add('d-none');
  new bootstrap.Modal(document.getElementById('editTeacherModal')).show();
}

document.getElementById('edit-teacher-btn').addEventListener('click', async () => {
  const form = document.getElementById('edit-teacher-form');
  const err = document.getElementById('edit-teacher-error');
  err.classList.add('d-none');
  const body = new URLSearchParams(new FormData(form));
  const res = await fetch(`/api/admin/teachers/${editTeacherId}`, { method: 'PUT', headers: formHeaders(), body });
  if (res.ok) {
    bootstrap.Modal.getInstance(document.getElementById('editTeacherModal')).hide();
    loadTeachers();
  } else {
    const e = await res.json(); err.textContent = e.detail || 'Ошибка'; err.classList.remove('d-none');
  }
});

async function resetTeacherPassword(id) {
  if (!confirm('Сбросить пароль преподавателя?')) return;
  const res = await fetch(`/api/admin/teachers/${id}/reset-password`, { method: 'POST', headers: authHeaders() });
  if (res.ok) {
    const data = await res.json();
    document.getElementById('temp-teacher-password-value').textContent = data.temp_password;
    document.getElementById('temp-teacher-password-alert').classList.remove('d-none');
  }
}

async function deleteTeacher(id) {
  if (!confirm('Удалить преподавателя?')) return;
  await fetch(`/api/admin/teachers/${id}`, { method: 'DELETE', headers: authHeaders() });
  loadTeachers(); loadStats();
}

// Вызываются из inline onclick в таблице
window.openEditTeacher = openEditTeacher;
window.resetTeacherPassword = resetTeacherPassword;
window.deleteTeacher = deleteTeacher;
