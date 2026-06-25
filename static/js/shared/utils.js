// Общие утилиты: экранирование HTML и всплывающие уведомления (toast).

export function escapeHtml(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export function showToast(msg, type = 'success') {
  const el = document.getElementById('app-toast');
  el.className = `toast align-items-center text-bg-${type} border-0`;
  document.getElementById('app-toast-body').textContent = msg;
  bootstrap.Toast.getOrCreateInstance(el, { delay: 3500 }).show();
}

// Бейдж дедлайна (используется кабинетами студента и преподавателя)
export function deadlineBadge(deadlineStr) {
  if (!deadlineStr) return '<span class="badge bg-secondary">Без дедлайна</span>';
  const now = new Date(); now.setHours(0, 0, 0, 0);
  const due = new Date(deadlineStr);
  const days = Math.round((due - now) / 86400000);
  if (days < 0) return `<span class="badge bg-danger">Просрочено (${due.toLocaleDateString('ru-RU')})</span>`;
  if (days <= 7) return `<span class="badge bg-warning text-dark">Дедлайн: ${due.toLocaleDateString('ru-RU')} (${days} дн.)</span>`;
  return `<span class="badge bg-success">Дедлайн: ${due.toLocaleDateString('ru-RU')}</span>`;
}
