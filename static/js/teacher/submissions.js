// Работы студентов: статистика, карточки, фильтры, файлы, выставление статуса,
// сообщение студенту.
import { escapeHtml, showToast, deadlineBadge } from '../shared/utils.js';
import { getAuthHeaders, logoutToLogin } from './api.js';

let allSubmissions = [];

function deadlineSortKey(deadlineStr) {
  if (!deadlineStr) return Infinity;
  const now = new Date(); now.setHours(0, 0, 0, 0);
  return Math.round((new Date(deadlineStr) - now) / 86400000);
}

const STRIP_COLORS = { submitted:'#adb5bd', in_review:'#ffc107', resubmitted:'#0d6efd', notebook_sent:'#0dcaf0', approved:'#198754', rejected:'#dc3545' };
const STATUS_BADGE = {
  submitted:     '<span class="badge" style="background:#e9ecef;color:#495057;font-weight:500;">Отправлено</span>',
  in_review:     '<span class="badge" style="background:#fff3cd;color:#856404;font-weight:500;">На проверке</span>',
  resubmitted:   '<span class="badge" style="background:#cfe2ff;color:#084298;font-weight:500;">Повторно</span>',
  notebook_sent: '<span class="badge" style="background:#d0f4f5;color:#055160;font-weight:500;">Тетрадь отправлена</span>',
  approved:      '<span class="badge" style="background:#d1e7dd;color:#0a3622;font-weight:500;">Зачтено</span>',
  rejected:      '<span class="badge" style="background:#f8d7da;color:#58151c;font-weight:500;">Не зачтено</span>',
};

export async function loadTeacherStats() {
  const res = await fetch('/api/teacher/stats/me', { headers: getAuthHeaders() });
  if (!res.ok) return;
  const d = await res.json();
  document.getElementById('tc-stat-pending').textContent = d.pending;
  document.getElementById('tc-stat-overdue').textContent = d.overdue;
  document.getElementById('tc-stat-subjects').textContent = d.subjects;
}

document.getElementById('tc-pending-card').addEventListener('click', () => {
  document.getElementById('filter-status').value = 'pending';
  renderSubmissionCards();
  document.querySelector('.section-card').scrollIntoView({ behavior: 'smooth', block: 'start' });
});
document.getElementById('tc-overdue-card').addEventListener('click', () => {
  document.getElementById('filter-status').value = 'overdue';
  renderSubmissionCards();
  document.querySelector('.section-card').scrollIntoView({ behavior: 'smooth', block: 'start' });
});

export async function loadSubmissions() {
  try {
    const res = await fetch('/api/teacher/assignments/me', { headers: getAuthHeaders() });
    if (res.status === 401 || res.status === 403) {
      logoutToLogin(); return;
    }
    if (!res.ok) throw new Error('Ошибка загрузки работ');
    allSubmissions = await res.json();
    allSubmissions.sort((a, b) => deadlineSortKey(a.deadline) - deadlineSortKey(b.deadline));

    const subjectFilter = document.getElementById('filter-subject');
    const saved = subjectFilter.value;
    subjectFilter.innerHTML = '<option value="">Все предметы</option>';
    [...new Set(allSubmissions.map(s => s.subject).filter(Boolean))].sort().forEach(s => {
      const opt = document.createElement('option');
      opt.value = s; opt.textContent = s;
      if (s === saved) opt.selected = true;
      subjectFilter.appendChild(opt);
    });

    renderSubmissionCards();
  } catch (err) {
    console.error('Ошибка при загрузке работ:', err);
    logoutToLogin();
  }
}

function renderSubmissionCards() {
  const subject = document.getElementById('filter-subject').value;
  const status  = document.getElementById('filter-status').value;

  const filtered = allSubmissions.filter(row => {
    if (subject && row.subject !== subject) return false;
    if (status === 'pending')       return ['submitted','in_review','resubmitted','notebook_sent'].includes(row.last_status);
    if (status === 'overdue')       return deadlineSortKey(row.deadline) < 0 && row.last_status !== 'approved';
    if (status === 'approved')      return row.last_status === 'approved';
    if (status === 'rejected')      return row.last_status === 'rejected';
    if (status === 'not_submitted') return !row.last_status;
    return true;
  });

  const container = document.getElementById('submissions-cards');
  const empty     = document.getElementById('submissions-empty');
  container.innerHTML = '';
  document.getElementById('filter-count').textContent = filtered.length ? `${filtered.length} работ` : '';

  if (filtered.length === 0) { empty.style.display = 'block'; return; }
  empty.style.display = 'none';

  filtered.forEach(row => {
    const strip  = STRIP_COLORS[row.last_status] || '#e9ecef';
    const badge  = row.last_status ? (STATUS_BADGE[row.last_status] || `<span class="badge bg-secondary">${escapeHtml(row.last_status_label || row.last_status)}</span>`) : '<span class="badge" style="background:#e9ecef;color:#6c757d;font-weight:500;">Не сдано</span>';
    const isNb   = row.submission_type === 'notebook';
    const typeBadge = isNb
      ? `<span class="badge rounded-pill" style="background:#fff3cd;color:#856404;border:1px solid #ffc107;font-size:.68rem;"><i class="bi bi-book me-1"></i>Тетрадь</span>`
      : `<span class="badge rounded-pill" style="background:#cfe2ff;color:#084298;border:1px solid #9ec5fe;font-size:.68rem;"><i class="bi bi-file-earmark-text me-1"></i>Эл.</span>`;
    const filesEl = isNb
      ? `<span class="text-muted" style="font-size:.8rem;"><i class="bi bi-envelope me-1"></i>Почтой</span>`
      : `<button class="btn btn-sm btn-outline-primary view-files" data-assignment-id="${row.assignment_id}" data-student-id="${escapeHtml(row.student_id)}" title="Файлы"><i class="bi bi-paperclip"></i></button>`;

    const col = document.createElement('div');
    col.className = 'col-12 col-md-6 col-xl-4';
    col.innerHTML = `
      <div class="sub-card">
        <div class="sub-card-strip" style="background:${strip};"></div>
        <div class="sub-card-body">
          <div class="d-flex justify-content-between align-items-start mb-2 gap-2">
            <div style="min-width:0;">
              <div class="fw-semibold text-truncate">${escapeHtml(row.student_name)}</div>
              <div class="text-muted" style="font-size:.78rem;">${escapeHtml(row.student_id)}</div>
            </div>
            <div class="d-flex flex-column align-items-end gap-1 flex-shrink-0">
              ${badge}${typeBadge}
            </div>
          </div>
          <div class="mb-2" style="font-size:.83rem;">
            <span class="text-muted">${escapeHtml(row.subject)}</span>
            <span class="mx-1 text-muted">·</span>
            <span class="fw-medium">${escapeHtml(row.title)}</span>
          </div>
          <div class="mb-3">${deadlineBadge(row.deadline)}</div>
          <div class="mt-auto d-flex gap-2 pt-2 border-top align-items-center">
            ${filesEl}
            <div class="ms-auto d-flex gap-1">
              <button class="btn btn-sm btn-outline-success set-grade"
                data-student-id="${escapeHtml(row.student_id)}"
                data-subject-name="${escapeHtml(row.subject)}"
                data-assignment-id="${row.assignment_id}"
                data-submission-type="${escapeHtml(row.submission_type || 'electronic')}"
                data-student-name="${escapeHtml(row.student_name)}"
                data-assignment-title="${escapeHtml(row.title)}"
                title="Выставить статус">
                <i class="bi bi-pencil-square"></i>
              </button>
              <button class="btn btn-sm btn-outline-primary send-msg-btn"
                data-student-db-id="${row.student_db_id}"
                data-student-name="${escapeHtml(row.student_name)}"
                title="Написать студенту">
                <i class="bi bi-envelope"></i>
              </button>
            </div>
          </div>
        </div>
      </div>`;
    container.appendChild(col);
  });

  container.querySelectorAll('.view-files').forEach(btn => {
    btn.addEventListener('click', async e => {
      const b = e.currentTarget;
      const r = await fetch(`/api/teacher/files/${b.dataset.assignmentId}/${b.dataset.studentId}`, { headers: getAuthHeaders() });
      const files = await r.json();
      const filesList = document.getElementById('files-list');
      filesList.innerHTML = files.length === 0 ? '<p class="text-muted">Файлы не найдены</p>' : '';
      files.forEach(f => {
        const btn2 = document.createElement('button');
        btn2.className = 'btn btn-sm btn-outline-secondary w-100 mb-2';
        btn2.innerHTML = `<i class="bi bi-paperclip me-1"></i>${escapeHtml(f.name)}`;
        btn2.onclick = async () => {
          try {
            const r2 = await fetch(`/download/${f.path}`, { headers: getAuthHeaders() });
            if (!r2.ok) throw new Error();
            const blob = await r2.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a'); a.href = url; a.download = f.name;
            document.body.appendChild(a); a.click(); window.URL.revokeObjectURL(url); a.remove();
          } catch { showToast('Не удалось скачать файл', 'danger'); }
        };
        filesList.appendChild(btn2);
      });
      bootstrap.Modal.getOrCreateInstance(document.getElementById('filesModal')).show();
    });
  });

  container.querySelectorAll('.send-msg-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      const b = e.currentTarget;
      document.getElementById('msg-student-db-id').value = b.dataset.studentDbId;
      document.getElementById('msg-student-label').textContent = `Получатель: ${b.dataset.studentName}`;
      document.getElementById('teacher-msg-form').reset();
      document.getElementById('msg-student-db-id').value = b.dataset.studentDbId;
      bootstrap.Modal.getOrCreateInstance(document.getElementById('sendMsgModal')).show();
    });
  });

  container.querySelectorAll('.set-grade').forEach(btn => {
    btn.addEventListener('click', e => {
      const b = e.currentTarget;
      document.getElementById('modal-student-id').value = b.dataset.studentId;
      document.getElementById('modal-subject-name').value = b.dataset.subjectName;
      document.getElementById('modal-assignment-id').value = b.dataset.assignmentId;
      document.getElementById('grade-modal-context').textContent = `${b.dataset.studentName} · ${b.dataset.assignmentTitle}`;
      document.getElementById('review').value = '';
      document.getElementById('feedback-file').value = '';
      document.getElementById('feedback-file-block').style.display = 'none';
      const isNb2 = b.dataset.submissionType === 'notebook';
      const sel = document.getElementById('status-input');
      sel.innerHTML = isNb2
        ? `<option value="получена">Получена</option><option value="зачёт">Зачтено</option><option value="не зачтено">Не зачтено</option>`
        : `<option value="принят на рассмотрение">Принят на рассмотрение</option><option value="зачёт">Зачёт</option><option value="не зачтено">Не зачтено</option>`;
      sel.onchange = () => {
        document.getElementById('feedback-file-block').style.display = (!isNb2 && sel.value === 'не зачтено') ? 'block' : 'none';
        if (sel.value !== 'не зачтено') document.getElementById('feedback-file').value = '';
      };
      bootstrap.Modal.getOrCreateInstance(document.getElementById('gradeModal')).show();
    });
  });
}

document.getElementById('filter-subject').addEventListener('change', renderSubmissionCards);
document.getElementById('filter-status').addEventListener('change', renderSubmissionCards);
document.getElementById('refresh-btn').addEventListener('click', () => { loadSubmissions(); loadTeacherStats(); });

document.getElementById('grade-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const studentId = document.getElementById('modal-student-id').value;
  const subjectName = document.getElementById('modal-subject-name').value;
  const assignmentId = document.getElementById('modal-assignment-id').value;
  const statusInput = document.getElementById('status-input').value;
  const review = document.getElementById('review').value;
  const feedbackFile = document.getElementById('feedback-file').files[0];

  const gradeRes = await fetch('/api/teacher/grade', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', ...getAuthHeaders() },
    body: new URLSearchParams({ student_id: studentId, subject_name: subjectName, assignment_id: assignmentId, status_input: statusInput, review })
  });
  if (!gradeRes.ok) {
    if (gradeRes.status === 401 || gradeRes.status === 403) { logoutToLogin(); return; }
    const error = await gradeRes.json().catch(() => ({ detail: 'Ошибка' }));
    showToast('Ошибка: ' + (error.detail || 'Неизвестная ошибка'), 'danger');
    return;
  }
  if (statusInput === 'не зачтено' && feedbackFile) {
    const formData = new FormData(); formData.append('file', feedbackFile);
    const feedbackRes = await fetch(`/api/teacher/feedback/${assignmentId}/${studentId}`, { method: 'POST', headers: getAuthHeaders(), body: formData });
    if (!feedbackRes.ok) showToast('Файл комментария не сохранён', 'warning');
  }
  showToast('Статус сохранён');
  bootstrap.Modal.getInstance(document.getElementById('gradeModal')).hide();
  loadSubmissions();
  loadTeacherStats();
});

document.getElementById('teacher-msg-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = new URLSearchParams({
    student_id: document.getElementById('msg-student-db-id').value,
    title: document.getElementById('msg-title-teacher').value,
    body: document.getElementById('msg-body-teacher').value,
  });
  const res = await fetch('/api/messages/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', ...getAuthHeaders() },
    body
  });
  if (res.ok) {
    bootstrap.Modal.getInstance(document.getElementById('sendMsgModal')).hide();
    showToast('Сообщение отправлено', 'success');
  } else {
    showToast('Ошибка отправки', 'danger');
  }
});
