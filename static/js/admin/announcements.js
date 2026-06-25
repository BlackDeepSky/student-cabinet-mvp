// Объявления (баннер) и личные сообщения студентам.
import { escapeHtml, showToast } from '../shared/utils.js';
import { authHeaders, formHeaders } from '../shared/api.js';
import { makePendingList, setupMultiAc } from '../shared/autocomplete.js';
import { state } from './state.js';

const msgStudentList = makePendingList('msg-student', null);

setupMultiAc('msg-student-autocomplete', 'msg-student-ac-list',
  () => state.allStudents.map(s => ({ value: s.id, label: `${s.last_name} ${s.first_name} (${s.student_id})` })),
  msgStudentList, item => msgStudentList.add(item));

export async function loadAnnouncements() {
  const res = await fetch('/api/admin/announcements', { headers: authHeaders() });
  if (!res.ok) return;
  const list = await res.json();
  const el = document.getElementById('ann-list');
  if (list.length === 0) { el.innerHTML = '<p class="text-muted small">Нет объявлений</p>'; return; }
  el.innerHTML = list.map(a => `
    <div class="border rounded p-2 mb-2 ${a.is_active ? '' : 'opacity-50'}">
      <div class="d-flex justify-content-between align-items-start">
        <strong style="font-size:.9rem">${escapeHtml(a.title)}</strong>
        <button class="btn btn-outline-danger btn-sm py-0 px-1 ms-2" onclick="deleteAnnouncement(${a.id})" title="Удалить"><i class="bi bi-trash"></i></button>
      </div>
      <p class="mb-1 text-muted" style="font-size:.85rem;white-space:pre-wrap">${escapeHtml(a.body)}</p>
      <small class="text-muted">${a.expires_at ? 'До ' + a.expires_at : 'Без срока'} · ${new Date(a.created_at).toLocaleDateString('ru-RU')}</small>
    </div>`).join('');
}

async function deleteAnnouncement(id) {
  if (!confirm('Удалить объявление?')) return;
  await fetch(`/api/admin/announcements/${id}`, { method: 'DELETE', headers: authHeaders() });
  loadAnnouncements();
}

document.getElementById('ann-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const params = new URLSearchParams();
  params.append('title', document.getElementById('ann-title').value);
  params.append('body', document.getElementById('ann-body').value);
  const exp = document.getElementById('ann-expires').value;
  if (exp) params.append('expires_at', exp);
  const res = await fetch('/api/admin/announcements', { method: 'POST', headers: formHeaders(), body: params });
  if (res.ok) {
    e.target.reset();
    loadAnnouncements();
    showToast('Объявление опубликовано');
  } else {
    showToast('Ошибка', 'danger');
  }
});

export function loadStudentsForMsgSelect() {
  msgStudentList.clear();
  const inp = document.getElementById('msg-student-autocomplete');
  if (inp) inp.value = '';
  const lst = document.getElementById('msg-student-ac-list');
  if (lst) lst.style.display = 'none';
}

document.getElementById('msg-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const ids = msgStudentList.getValues();
  if (!ids.length) { showToast('Выберите студентов', 'warning'); return; }
  const title = document.getElementById('msg-title').value;
  const msgBody = document.getElementById('msg-body').value;
  await Promise.all(ids.map(id =>
    fetch('/api/messages/send', {
      method: 'POST',
      headers: { ...authHeaders(), 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ student_id: id, title, body: msgBody })
    })
  ));
  e.target.reset();
  msgStudentList.clear();
  showToast('Сообщение отправлено');
});

document.getElementById('ann-tab-btn').addEventListener('click', () => {
  loadAnnouncements();
  loadStudentsForMsgSelect();
});

// Вызывается из inline onclick в списке объявлений
window.deleteAnnouncement = deleteAnnouncement;
