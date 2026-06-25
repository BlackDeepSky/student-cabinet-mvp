// Сообщения студенту: счётчик непрочитанных, список с группировкой, фильтр.
import { escapeHtml } from '../shared/utils.js';
import { getAuthHeaders } from './api.js';

let messagesData = [];
let msgFilter = 'all';

const MONTHS_RU = ['Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'];

export async function loadUnreadCount() {
  try {
    const res = await fetch('/api/messages/me/unread-count', { headers: getAuthHeaders() });
    if (!res.ok) return;
    const { count } = await res.json();
    const badge = document.getElementById('messages-badge');
    if (count > 0) {
      badge.textContent = count > 9 ? '9+' : count;
      badge.classList.remove('d-none');
    } else {
      badge.classList.add('d-none');
    }
  } catch {}
}

function renderMessages(msgs) {
  const list = document.getElementById('messages-list');
  const emptyEl = document.getElementById('messages-empty');
  list.innerHTML = '';
  if (msgs.length === 0) { emptyEl.classList.remove('d-none'); return; }
  emptyEl.classList.add('d-none');

  const groups = {};
  msgs.forEach(m => {
    const d = new Date(m.created_at);
    const key = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;
    if (!groups[key]) groups[key] = { label: `${MONTHS_RU[d.getMonth()]} ${d.getFullYear()}`, msgs: [] };
    groups[key].msgs.push(m);
  });

  Object.keys(groups).sort().reverse().forEach(key => {
    const hdr = document.createElement('div');
    hdr.className = 'px-3 py-2 bg-light border-bottom fw-semibold text-muted';
    hdr.style.cssText = 'font-size:.78rem;letter-spacing:.04em;text-transform:uppercase;';
    hdr.textContent = groups[key].label;
    list.appendChild(hdr);

    groups[key].msgs.forEach(m => {
      const date = new Date(m.created_at).toLocaleDateString('ru-RU', { day:'2-digit', month:'long', year:'numeric' });
      const senderIcon = m.sender_type === 'admin' ? 'bi-shield-fill' : 'bi-person-fill';
      const div = document.createElement('div');
      div.className = `p-3 border-bottom ${m.is_read ? '' : 'bg-light'}`;
      div.innerHTML = `
        <div class="d-flex justify-content-between align-items-start mb-1">
          <span class="fw-semibold">${m.is_read ? '' : '<span class="badge bg-primary me-1" style="font-size:.65rem">Новое</span>'}${escapeHtml(m.title)}</span>
          <small class="text-muted ms-2 flex-shrink-0">${date}</small>
        </div>
        <p class="mb-1 text-muted" style="font-size:.9rem; white-space:pre-wrap">${escapeHtml(m.body)}</p>
        <small class="text-muted"><i class="bi ${senderIcon} me-1"></i>${escapeHtml(m.sender_name)}</small>`;
      if (!m.is_read) {
        div.addEventListener('click', async () => {
          await fetch(`/api/messages/${m.id}/read`, { method: 'PUT', headers: getAuthHeaders() });
          div.classList.remove('bg-light');
          div.querySelector('.badge')?.remove();
          loadUnreadCount();
        }, { once: true });
      }
      list.appendChild(div);
    });
  });
}

function applyMsgFilter() {
  const filtered = msgFilter === 'all' ? messagesData
    : messagesData.filter(m => m.sender_type === msgFilter);
  renderMessages(filtered);
}

async function loadMessages() {
  const list = document.getElementById('messages-list');
  const emptyEl = document.getElementById('messages-empty');
  list.innerHTML = '';
  emptyEl.classList.add('d-none');
  try {
    const res = await fetch('/api/messages/me', { headers: getAuthHeaders() });
    if (!res.ok) throw new Error();
    messagesData = await res.json();
    msgFilter = 'all';
    document.querySelectorAll('#msg-filter-group button').forEach(b => b.classList.remove('active'));
    document.querySelector('#msg-filter-group [data-filter="all"]').classList.add('active');
    applyMsgFilter();
  } catch {
    list.innerHTML = '<p class="text-danger text-center py-3">Ошибка загрузки</p>';
  }
}

document.getElementById('msg-filter-group').addEventListener('click', e => {
  const btn = e.target.closest('button[data-filter]');
  if (!btn) return;
  msgFilter = btn.dataset.filter;
  document.querySelectorAll('#msg-filter-group button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyMsgFilter();
});

document.getElementById('messages-btn').addEventListener('click', () => {
  loadMessages();
  bootstrap.Modal.getOrCreateInstance(document.getElementById('messagesModal')).show();
});
