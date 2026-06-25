// История зачтённых работ.
import { escapeHtml, showToast } from '../shared/utils.js';
import { getAuthHeaders, logoutToLogin } from './api.js';

let historyData = [];

async function loadHistory() {
  try {
    const res = await fetch('/api/teacher/history/me', { headers: getAuthHeaders() });
    if (res.status === 401 || res.status === 403) { logoutToLogin(); return; }
    if (!res.ok) throw new Error('Ошибка загрузки истории');
    historyData = await res.json();
    document.getElementById('history-search').value = '';
    renderHistory(historyData);
    bootstrap.Modal.getOrCreateInstance(document.getElementById('historyModal')).show();
  } catch (err) {
    showToast('Ошибка загрузки истории: ' + err.message, 'danger');
  }
}

document.getElementById('history-search').addEventListener('input', function () {
  const q = this.value.toLowerCase().trim();
  renderHistory(q ? historyData.filter(item =>
    item.student_name.toLowerCase().includes(q) || item.student_id.toLowerCase().includes(q)
  ) : historyData);
});

function renderHistory(items) {
  const list = document.getElementById('history-list');
  const emptyMsg = document.getElementById('history-empty');
  list.innerHTML = '';
  if (items.length === 0) { emptyMsg.style.display = 'block'; return; }
  emptyMsg.style.display = 'none';
  items.forEach(item => {
    const isNotebook = item.submission_type === 'notebook';
    const typeBadge = isNotebook
      ? `<span class="badge rounded-pill" style="background:#fff3cd;color:#856404;border:1px solid #ffc107;font-weight:500;font-size:.72rem;"><i class="bi bi-book me-1"></i>Тетрадь</span>`
      : `<span class="badge rounded-pill" style="background:#cfe2ff;color:#084298;border:1px solid #9ec5fe;font-weight:500;font-size:.72rem;"><i class="bi bi-file-earmark-text me-1"></i>Электронная</span>`;
    const filesBtn = !isNotebook
      ? `<button class="btn btn-sm btn-outline-primary history-view-files" data-assignment-id="${item.assignment_id}" data-student-id="${escapeHtml(item.student_id)}"><i class="bi bi-paperclip me-1"></i>Файлы</button>`
      : '';
    const dateStr = item.graded_at ? new Date(item.graded_at).toLocaleString('ru-RU', { day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit' }) : '—';
    const card = document.createElement('div');
    card.className = 'history-card border rounded-3 p-3 mb-2';
    card.style.cssText = 'background:#fff;transition:box-shadow .15s;';
    card.innerHTML = `
      <div class="d-flex justify-content-between align-items-start gap-2 flex-wrap">
        <div>
          <div class="fw-semibold">${escapeHtml(item.student_name)}</div>
          <div class="text-muted" style="font-size:.8rem;">${escapeHtml(item.student_id)}</div>
        </div>
        ${typeBadge}
      </div>
      <div class="mt-2" style="font-size:.85rem;">
        <span class="text-muted">${escapeHtml(item.subject)}</span>
        <span class="mx-1 text-muted">·</span>
        <span>${escapeHtml(item.assignment_title)}</span>
      </div>
      <div class="d-flex justify-content-between align-items-center mt-2 flex-wrap gap-1">
        <small class="text-muted"><i class="bi bi-calendar-check me-1"></i>${dateStr}</small>
        ${filesBtn}
      </div>`;
    list.appendChild(card);
  });
  list.querySelectorAll('.history-view-files').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const b = e.currentTarget;
      const res = await fetch(`/api/teacher/files/${b.dataset.assignmentId}/${b.dataset.studentId}`, { headers: getAuthHeaders() });
      const files = await res.json();
      const filesList = document.getElementById('files-list');
      filesList.innerHTML = files.length === 0 ? '<p class="text-muted">Файлы не найдены</p>' : '';
      files.forEach(f => {
        const button = document.createElement('button');
        button.className = 'btn btn-sm btn-outline-secondary w-100 mb-2';
        button.innerHTML = `<i class="bi bi-paperclip me-1"></i>${escapeHtml(f.name)}`;
        button.onclick = async () => {
          const r = await fetch(`/download/${f.path}`, { headers: getAuthHeaders() });
          if (!r.ok) { showToast('Ошибка скачивания', 'danger'); return; }
          const blob = await r.blob();
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a'); a.href = url; a.download = f.name;
          document.body.appendChild(a); a.click(); window.URL.revokeObjectURL(url); a.remove();
        };
        filesList.appendChild(button);
      });
      bootstrap.Modal.getOrCreateInstance(document.getElementById('filesModal')).show();
    });
  });
}

document.getElementById('show-history-btn').addEventListener('click', loadHistory);
