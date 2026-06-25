// Точка входа админки: вход/выход, смена пароля, вкладки, начальная загрузка.
// Импорт модулей ниже также выполняет их код (навешивание обработчиков).
import { getToken, setToken, clearToken, formHeaders } from '../shared/api.js';
import { showToast } from '../shared/utils.js';
import { loadStudents } from './students.js';
import { loadTeachers } from './teachers.js';
import { loadSubjects } from './subjects.js';
import { loadAssignments } from './assignments.js';
import { loadStats, loadAuditLog } from './dashboard.js';
import { loadAnnouncements, loadStudentsForMsgSelect } from './announcements.js';

// Вход
document.getElementById('login-form').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = e.target.querySelector('button[type=submit]');
  btn.disabled = true;
  const errEl = document.getElementById('login-error');
  errEl.classList.add('d-none');
  const body = new URLSearchParams({ admin_id: document.getElementById('admin-id').value, password: document.getElementById('admin-password').value });
  const res = await fetch('/api/admin/login', { method: 'POST', body });
  if (res.ok) {
    const data = await res.json();
    setToken(data.token);
    showMain();
  } else {
    errEl.textContent = 'Неверный логин или пароль';
    errEl.classList.remove('d-none');
  }
  btn.disabled = false;
});

document.getElementById('logout-btn').addEventListener('click', () => {
  clearToken();
  document.getElementById('app-navbar').style.display = 'none';
  document.getElementById('main-section').style.display = 'none';
  document.getElementById('login-section').style.display = 'flex';
});

document.getElementById('change-admin-pw-btn').addEventListener('click', async () => {
  const errEl = document.getElementById('change-admin-pw-error');
  errEl.classList.add('d-none');
  const oldPw = document.getElementById('admin-pw-old').value;
  const newPw = document.getElementById('admin-pw-new').value;
  const confirmPw = document.getElementById('admin-pw-confirm').value;
  if (newPw.length < 8) { errEl.textContent = 'Новый пароль должен содержать минимум 8 символов'; errEl.classList.remove('d-none'); return; }
  if (newPw !== confirmPw) { errEl.textContent = 'Пароли не совпадают'; errEl.classList.remove('d-none'); return; }
  const btn = document.getElementById('change-admin-pw-btn');
  btn.disabled = true;
  const body = new URLSearchParams({ old_password: oldPw, new_password: newPw });
  const res = await fetch('/api/admin/change-password', { method: 'POST', headers: formHeaders(), body });
  btn.disabled = false;
  if (res.ok) {
    bootstrap.Modal.getInstance(document.getElementById('changeAdminPasswordModal')).hide();
    document.getElementById('admin-pw-old').value = '';
    document.getElementById('admin-pw-new').value = '';
    document.getElementById('admin-pw-confirm').value = '';
    showToast('Пароль успешно изменён');
  } else {
    const err = await res.json().catch(() => ({ detail: 'Ошибка' }));
    errEl.textContent = err.detail || 'Ошибка при смене пароля';
    errEl.classList.remove('d-none');
  }
});

function showMain() {
  document.getElementById('login-section').style.display = 'none';
  document.getElementById('main-section').style.display = '';
  document.getElementById('app-navbar').style.display = 'flex';
  loadAll();
}

async function loadAll() {
  await Promise.all([loadStudents(), loadTeachers(), loadSubjects(), loadAssignments(), loadStats()]);
}

// Mobile dropdown: activate the corresponding Bootstrap tab
document.querySelectorAll('#mobile-section-menu .dropdown-item').forEach(btn => {
  btn.addEventListener('click', function () {
    const target = this.dataset.target;
    const tabBtn = document.querySelector(`#adminTabs [data-bs-target="${target}"]`);
    if (tabBtn) bootstrap.Tab.getOrCreateInstance(tabBtn).show();
  });
});

// Sync dropdown label whenever any tab becomes active (desktop click OR mobile dropdown)
document.querySelectorAll('#adminTabs [data-bs-toggle="tab"]').forEach(tabEl => {
  tabEl.addEventListener('shown.bs.tab', () => {
    const target = tabEl.getAttribute('data-bs-target');
    // Special side-effects
    if (target === '#tab-audit') loadAuditLog();
    if (target === '#tab-announcements') { loadAnnouncements(); loadStudentsForMsgSelect(); }
    // Update mobile dropdown
    const item = document.querySelector(`#mobile-section-menu [data-target="${target}"]`);
    if (!item) return;
    const icon = item.dataset.icon;
    const iconColor = item.dataset.iconColor || '';
    const label = item.dataset.label;
    document.getElementById('mobile-section-label').innerHTML =
      `<i class="bi ${icon} me-2 ${iconColor}"></i>${label}`;
    document.querySelectorAll('#mobile-section-menu .dropdown-item').forEach(i => i.classList.remove('active'));
    item.classList.add('active');
  });
});

// Инициализация
if (getToken()) showMain();
else document.getElementById('login-section').style.display = 'flex';
