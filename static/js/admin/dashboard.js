// Дашборд: статистика, детали «на проверке»/«просрочено», журнал аудита.
import { escapeHtml } from '../shared/utils.js';
import { authHeaders } from '../shared/api.js';

export async function loadStats() {
  const res = await fetch('/api/admin/stats', { headers: authHeaders() });
  if (!res.ok) return;
  const d = await res.json();
  document.getElementById('stat-students').textContent = d.students;
  document.getElementById('stat-teachers').textContent = d.teachers;
  document.getElementById('stat-pending').textContent = d.pending;
  document.getElementById('stat-overdue').textContent = d.overdue;
}

const PENDING_STATUS = { submitted: 'Отправлено', in_review: 'На проверке', resubmitted: 'Повторно отправлено', notebook_sent: 'Тетрадь отправлена' };
const PENDING_STATUS_COLOR = { submitted: '#6c757d', in_review: '#856404', resubmitted: '#0a3622', notebook_sent: '#055160' };

async function loadPendingDetails() {
  const res = await fetch('/api/admin/pending-details', { headers: authHeaders() });
  if (!res.ok) return;
  const items = await res.json();
  const list = document.getElementById('pending-detail-list');
  const empty = document.getElementById('pending-detail-empty');
  list.innerHTML = '';
  if (items.length === 0) { empty.style.display = 'block'; }
  else {
    empty.style.display = 'none';
    items.forEach(item => {
      const statusLabel = PENDING_STATUS[item.status] || item.status;
      const statusColor = PENDING_STATUS_COLOR[item.status] || '#6c757d';
      const dateStr = item.submitted_at ? new Date(item.submitted_at).toLocaleString('ru-RU', { day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit' }) : '—';
      const typeIcon = item.submission_type === 'notebook' ? 'bi-book' : 'bi-file-earmark-text';
      const card = document.createElement('div');
      card.className = 'detail-card';
      card.innerHTML = `
        <div class="d-flex justify-content-between align-items-start flex-wrap gap-1">
          <div>
            <span class="fw-semibold">${escapeHtml(item.student_name)}</span>
            <span class="text-muted ms-1" style="font-size:.8rem;">${escapeHtml(item.student_id)}</span>
          </div>
          <span class="badge rounded-pill" style="background:${statusColor}20;color:${statusColor};border:1px solid ${statusColor}40;font-size:.72rem;font-weight:500;">${statusLabel}</span>
        </div>
        <div class="mt-1" style="font-size:.84rem;">
          <span class="text-muted">${escapeHtml(item.subject)}</span><span class="mx-1 text-muted">·</span><span>${escapeHtml(item.assignment_title)}</span>
          <i class="bi ${typeIcon} ms-1 text-muted" style="font-size:.8rem;"></i>
        </div>
        <div class="d-flex justify-content-between align-items-center mt-1 flex-wrap gap-1" style="font-size:.8rem;">
          <span class="text-muted"><i class="bi bi-person-workspace me-1"></i>${escapeHtml(item.teacher_name)}</span>
          <span class="text-muted"><i class="bi bi-clock me-1"></i>${dateStr}</span>
        </div>`;
      list.appendChild(card);
    });
  }
  bootstrap.Modal.getOrCreateInstance(document.getElementById('pendingDetailsModal')).show();
}

async function loadOverdueDetails() {
  const res = await fetch('/api/admin/overdue-details', { headers: authHeaders() });
  if (!res.ok) return;
  const items = await res.json();
  const list = document.getElementById('overdue-detail-list');
  const empty = document.getElementById('overdue-detail-empty');
  list.innerHTML = '';
  if (items.length === 0) { empty.style.display = 'block'; }
  else {
    empty.style.display = 'none';
    items.forEach(item => {
      const deadlineDate = new Date(item.deadline);
      const daysOverdue = Math.floor((Date.now() - deadlineDate) / 86400000);
      const deadlineStr = deadlineDate.toLocaleDateString('ru-RU', { day:'2-digit', month:'2-digit', year:'numeric' });
      const card = document.createElement('div');
      card.className = 'detail-card';
      card.innerHTML = `
        <div class="d-flex justify-content-between align-items-start flex-wrap gap-1">
          <div>
            <span class="fw-semibold">${escapeHtml(item.student_name)}</span>
            <span class="text-muted ms-1" style="font-size:.8rem;">${escapeHtml(item.student_id)}</span>
          </div>
          <span class="badge rounded-pill" style="background:#fee2e2;color:#dc2626;border:1px solid #fca5a5;font-size:.72rem;font-weight:500;">+${daysOverdue} дн.</span>
        </div>
        <div class="mt-1" style="font-size:.84rem;">
          <span class="text-muted">${escapeHtml(item.subject)}</span><span class="mx-1 text-muted">·</span><span>${escapeHtml(item.assignment_title)}</span>
        </div>
        <div class="d-flex justify-content-between align-items-center mt-1 flex-wrap gap-1" style="font-size:.8rem;">
          <span class="text-muted"><i class="bi bi-person-workspace me-1"></i>${escapeHtml(item.teacher_name)}</span>
          <span class="text-muted"><i class="bi bi-calendar-x me-1"></i>Срок: ${deadlineStr}</span>
        </div>`;
      list.appendChild(card);
    });
  }
  bootstrap.Modal.getOrCreateInstance(document.getElementById('overdueDetailsModal')).show();
}

document.getElementById('card-pending').addEventListener('click', loadPendingDetails);
document.getElementById('card-overdue').addEventListener('click', loadOverdueDetails);

const AUDIT_ICONS = {
  student:      { icon: 'bi-person',           color: '#1d6fef' },
  teacher:      { icon: 'bi-person-workspace',  color: '#059669' },
  subject:      { icon: 'bi-book',              color: '#7c3aed' },
  assignment:   { icon: 'bi-journal-text',      color: '#d97706' },
  announcement: { icon: 'bi-megaphone',         color: '#0891b2' },
  message:      { icon: 'bi-envelope',          color: '#db2777' },
};
const AUDIT_ACTION_COLOR = {
  'Добавлен': '#059669', 'Добавлено': '#059669',
  'Создано': '#059669',
  'Изменён': '#1d6fef', 'Изменено': '#1d6fef',
  'Назначен': '#1d6fef', 'Зачислен': '#1d6fef',
  'Массовое': '#1d6fef',
  'Сброс': '#d97706',
  'Снят': '#dc2626', 'Удалён': '#dc2626', 'Удалено': '#dc2626',
  'Отправлено': '#7c3aed',
};

export async function loadAuditLog() {
  const res = await fetch('/api/admin/audit-log', { headers: authHeaders() });
  if (!res.ok) return;
  const items = await res.json();
  const list = document.getElementById('audit-list');
  const empty = document.getElementById('audit-empty');
  list.innerHTML = '';
  if (items.length === 0) { empty.style.display = 'block'; return; }
  empty.style.display = 'none';
  items.forEach(item => {
    const meta = AUDIT_ICONS[item.entity] || { icon: 'bi-gear', color: '#6c757d' };
    const firstWord = item.action.split(' ')[0];
    const actionColor = AUDIT_ACTION_COLOR[firstWord] || '#6c757d';
    const dateStr = new Date(item.created_at).toLocaleString('ru-RU', { day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit' });
    const card = document.createElement('div');
    card.className = 'detail-card d-flex gap-3 align-items-start';
    card.innerHTML = `
      <div class="flex-shrink-0 d-flex align-items-center justify-content-center rounded-circle"
           style="width:36px;height:36px;background:${meta.color}18;">
        <i class="bi ${meta.icon}" style="color:${meta.color};font-size:1rem;"></i>
      </div>
      <div class="flex-grow-1 min-w-0">
        <div class="d-flex justify-content-between align-items-start flex-wrap gap-1">
          <span class="fw-semibold" style="color:${actionColor};font-size:.88rem;">${escapeHtml(item.action)}</span>
          <small class="text-muted flex-shrink-0">${dateStr}</small>
        </div>
        ${item.entity_name ? `<div style="font-size:.84rem;">${escapeHtml(item.entity_name)}</div>` : ''}
        ${item.details ? `<div class="text-muted" style="font-size:.78rem;">${escapeHtml(item.details)}</div>` : ''}
      </div>`;
    list.appendChild(card);
  });
}

document.getElementById('audit-refresh-btn').addEventListener('click', loadAuditLog);
