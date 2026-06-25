// Точка входа кабинета студента: вход/выход, смена пароля, инициализация.
import { getToken, getName, setSession, clearSession, showLogin, showMain, updateBadge } from './api.js';
import { loadAssignments } from './assignments.js';
import { loadAnnouncement } from './announcement.js';
import { loadUnreadCount } from './messages.js';
// Подключаем модуль успеваемости ради его обработчиков
import './grades.js';

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js');
}

window.addEventListener('load', () => {
  const token = getToken();
  const name = getName();
  if (token && name) {
    document.getElementById('student-name').textContent = name;
    loadAssignments();
    loadAnnouncement();
    loadUnreadCount();
    showMain();
    updateBadge();
  } else {
    showLogin();
  }
});

document.getElementById('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = e.target.querySelector('button[type=submit]');
  btn.disabled = true;
  const errEl = document.getElementById('login-error');
  errEl.classList.add('d-none');
  const studentId = document.getElementById('student-id').value.trim();
  const password = document.getElementById('password').value.trim();
  try {
    const res = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: `student_id=${encodeURIComponent(studentId)}&password=${encodeURIComponent(password)}`
    });
    if (!res.ok) throw new Error('Неверный номер студента или пароль');
    const data = await res.json();
    const fullName = `${data.user.last_name} ${data.user.first_name}${data.user.patronymic ? ' ' + data.user.patronymic : ''}`;
    setSession(data.token, fullName);
    document.getElementById('student-name').textContent = fullName;
    loadAssignments();
    loadAnnouncement();
    loadUnreadCount();
    showMain();
    updateBadge();
  } catch (err) {
    errEl.textContent = err.message;
    errEl.classList.remove('d-none');
  } finally {
    btn.disabled = false;
  }
});

document.getElementById('logout-btn').addEventListener('click', () => {
  clearSession();
  showLogin();
});

document.getElementById('cp-submit-btn').addEventListener('click', async () => {
  const alertEl = document.getElementById('change-password-alert');
  const oldPwd = document.getElementById('cp-old').value;
  const newPwd = document.getElementById('cp-new').value;
  const confirm = document.getElementById('cp-confirm').value;
  alertEl.className = 'alert d-none';
  if (newPwd !== confirm) {
    alertEl.className = 'alert alert-danger'; alertEl.textContent = 'Новые пароли не совпадают'; return;
  }
  if (newPwd.length < 8) {
    alertEl.className = 'alert alert-danger'; alertEl.textContent = 'Пароль должен содержать минимум 8 символов'; return;
  }
  const token = getToken();
  const res = await fetch('/api/change-password', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ old_password: oldPwd, new_password: newPwd })
  });
  if (res.ok) {
    alertEl.className = 'alert alert-success'; alertEl.textContent = 'Пароль успешно изменён';
    document.getElementById('change-password-form').reset();
  } else {
    const err = await res.json();
    alertEl.className = 'alert alert-danger'; alertEl.textContent = err.detail || 'Ошибка при смене пароля';
  }
});

document.getElementById('changePasswordModal').addEventListener('hidden.bs.modal', () => {
  document.getElementById('change-password-form').reset();
  document.getElementById('change-password-alert').className = 'alert d-none';
});
