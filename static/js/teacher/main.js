// Точка входа кабинета преподавателя: вход/выход, смена пароля, инициализация.
import { getToken, getName, setSession, clearSession, showLogin, showMain, updateBadge } from './api.js';
import { loadSubmissions, loadTeacherStats } from './submissions.js';
// Подключаем модули ради их обработчиков (история и прогресс самонавешиваются)
import './history.js';
import './progress.js';

if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');

window.addEventListener('load', () => {
  const token = getToken();
  const name = getName();
  if (token && name) {
    document.getElementById('teacher-name-nav').textContent = name;
    loadSubmissions();
    loadTeacherStats();
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
  const teacherId = document.getElementById('teacher-id').value.trim();
  const password = document.getElementById('password').value.trim();
  try {
    const res = await fetch('/api/teacher/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: `teacher_id=${encodeURIComponent(teacherId)}&password=${encodeURIComponent(password)}`
    });
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: 'Ошибка входа' }));
      throw new Error(error.detail || 'Неверные данные');
    }
    const data = await res.json();
    const fullName = `${data.user.last_name} ${data.user.first_name}${data.user.patronymic ? ' ' + data.user.patronymic : ''}`;
    setSession(data.token, fullName);
    document.getElementById('teacher-name-nav').textContent = fullName;
    loadSubmissions();
    loadTeacherStats();
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
  if (newPwd !== confirm) { alertEl.className = 'alert alert-danger'; alertEl.textContent = 'Новые пароли не совпадают'; return; }
  if (newPwd.length < 8) { alertEl.className = 'alert alert-danger'; alertEl.textContent = 'Пароль должен содержать минимум 8 символов'; return; }
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
    const err = await res.json(); alertEl.className = 'alert alert-danger'; alertEl.textContent = err.detail || 'Ошибка при смене пароля';
  }
});

document.getElementById('changePasswordModal').addEventListener('hidden.bs.modal', () => {
  document.getElementById('change-password-form').reset();
  document.getElementById('change-password-alert').className = 'alert d-none';
});
