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
