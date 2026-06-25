// Задания студента: рендер карточек, отправка работ, тетрадь, файлы обратной связи.
import { escapeHtml, showToast, deadlineBadge } from '../shared/utils.js';
import { getAuthHeaders, handleAuthError } from './api.js';

export async function loadAssignments() {
  try {
    const res = await fetch('/api/assignments/me', { headers: getAuthHeaders() });
    if (res.status === 401 || res.status === 403) { handleAuthError(); return; }
    if (!res.ok) throw new Error('Ошибка загрузки');
    const assignments = await res.json();
    const cont = document.getElementById('assignments');
    cont.innerHTML = '';

    if (assignments.length === 0) {
      cont.innerHTML = '<p class="text-muted">Нет активных заданий</p>';
      return;
    }

    for (const a of assignments) {
      const deadline = deadlineBadge(a.deadline);
      const submittedAt = a.submitted_at ? new Date(a.submitted_at).toLocaleDateString('ru-RU') : null;

      const isNotebook = a.submission_type === 'notebook';
      const statusCfgMap = {
        approved:      { icon: 'bi-check-circle-fill',    cls: 'strip-approved',      label: 'Зачтено' },
        in_review:     { icon: 'bi-hourglass-split',       cls: 'strip-in_review',     label: isNotebook ? 'Получена преподавателем' : 'На проверке' },
        rejected:      { icon: 'bi-x-circle-fill',         cls: 'strip-rejected',      label: 'Отклонено' },
        resubmitted:   { icon: 'bi-arrow-repeat',          cls: 'strip-resubmitted',   label: 'Повторная сдача' },
        submitted:     { icon: 'bi-cloud-check-fill',      cls: 'strip-submitted',     label: 'Отправлено' },
        notebook_sent: { icon: 'bi-envelope-check-fill',   cls: 'strip-notebook_sent', label: 'Тетрадь отправлена' },
      };
      const stripCfg = statusCfgMap[a.status] || { icon: 'bi-clock', cls: 'strip-pending', label: isNotebook ? 'Нет в кабинете' : 'Не отправлено' };
      const stripDate = submittedAt ? ` · ${submittedAt}` : '';
      const statusStrip = `<div class="card-status-strip ${stripCfg.cls}"><i class="bi ${stripCfg.icon}"></i>${stripCfg.label}${stripDate}</div>`;

      let reviewBlock = '';
      if ((a.status === 'rejected' || a.status === 'resubmitted') && a.review) {
        reviewBlock = `<div class="review-block"><strong>Рецензия:</strong> ${escapeHtml(a.review)}</div>`;
      }

      let feedbackBlock = '';
      if (a.feedback_files && a.feedback_files.length > 0) {
        const links = a.feedback_files.map(f =>
          `<button class="btn btn-sm btn-outline-info mt-1 me-1 download-feedback-file" data-file-id="${f.id}" data-file-name="${escapeHtml(f.name)}"><i class="bi bi-paperclip me-1"></i>${escapeHtml(f.name)}</button>`
        ).join('');
        feedbackBlock = `<div class="mt-2">${links}</div>`;
      }

      let actionBlock = '';
      if (isNotebook) {
        if (a.status === 'approved') {
          // зачтено — ничего не показываем
        } else if (a.status === 'in_review') {
          actionBlock = '<p class="text-muted mb-0 mt-2" style="font-size:.875rem"><i class="bi bi-envelope-check me-1"></i>Тетрадь получена преподавателем. Ожидайте результата.</p>';
        } else if (a.status === 'notebook_sent') {
          actionBlock = '<p class="text-muted mb-0 mt-2" style="font-size:.875rem"><i class="bi bi-envelope me-1"></i>Тетрадь отмечена как отправленная. Ожидайте получения.</p>';
        } else {
          const btnLabel = a.status === 'rejected' ? 'Отметить повторную отправку' : 'Отметить как отправлено почтой';
          actionBlock = `
            <div class="mt-2">
              <p class="text-muted mb-2" style="font-size:.875rem"><i class="bi bi-book me-1"></i>Выполните задание в тетради и отправьте её по почте. После отправки нажмите кнопку ниже.</p>
              <button type="button" class="btn btn-primary btn-sm notebook-send-btn" data-assignment-id="${a.id}">
                <i class="bi bi-envelope me-1"></i>${btnLabel}
              </button>
            </div>`;
        }
      } else if (a.status === 'approved') {
        // nothing
      } else if (a.final_grade_blocked) {
        const statusText = a.final_grade_status ? `Оценка выставлена: ${a.final_grade_status}.` : 'Оценка по предмету уже выставлена.';
        actionBlock = `<p class="text-muted mb-0 mt-2" style="font-size:.875rem">${statusText} Повторная сдача недоступна.</p>`;
      } else if (a.status === 'in_review') {
        actionBlock = '<p class="text-muted mb-0 mt-2" style="font-size:.875rem"><i class="bi bi-hourglass-split me-1"></i>Работа проверяется преподавателем</p>';
      } else {
        actionBlock = `
          <form class="submit-form mt-2" data-assignment-id="${a.id}">
            <input type="file" class="d-none file-input" multiple>
            <div class="file-list mb-2"></div>
            <div class="d-flex align-items-center gap-2 flex-wrap">
              <button type="button" class="btn btn-outline-secondary btn-sm add-files-btn">
                <i class="bi bi-paperclip me-1"></i>Добавить файлы
              </button>
              <span class="file-count text-muted" style="font-size:.85rem">0 / 10 файлов</span>
              <button type="submit" class="btn btn-primary btn-sm">
                <i class="bi bi-cloud-upload me-1"></i>Отправить
              </button>
            </div>
          </form>`;
      }

      const el = document.createElement('div');
      el.className = `assignment-card card card-status-${a.status || 'pending'}`;
      el.innerHTML = `
        ${statusStrip}
        <div class="card-body">
          <div class="subject-label">${escapeHtml(a.subject)}</div>
          <div class="teacher-label"><i class="bi bi-person me-1"></i>${escapeHtml(a.teachers)}</div>
          <h6 class="mb-1">${escapeHtml(a.title)}</h6>
          <p class="text-muted mb-2" style="font-size:.9rem">${escapeHtml(a.description)}</p>
          <div class="mb-1">${deadline}</div>
          ${reviewBlock}
          ${feedbackBlock}
          ${actionBlock}
        </div>`;
      cont.appendChild(el);
    }

    const MAX_FILES = 10;
    const formFileMaps = new Map();

    function renderFileList(form, files) {
      const list = form.querySelector('.file-list');
      const counter = form.querySelector('.file-count');
      counter.textContent = `${files.length} / ${MAX_FILES} файлов`;
      if (!files.length) { list.innerHTML = ''; return; }
      list.innerHTML = files.map((f, i) => `
        <div class="d-flex align-items-center gap-2 mb-1" style="font-size:.85rem">
          <i class="bi bi-file-earmark me-1 text-secondary"></i>
          <span class="text-truncate" style="max-width:240px" title="${f.name}">${f.name}</span>
          <span class="text-muted">(${(f.size/1024).toFixed(0)} КБ)</span>
          <button type="button" class="btn-close btn-sm remove-file-btn" style="font-size:.65rem" data-idx="${i}"></button>
        </div>`).join('');
      list.querySelectorAll('.remove-file-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          const assignmentId = form.dataset.assignmentId;
          const arr = formFileMaps.get(assignmentId) || [];
          arr.splice(parseInt(btn.dataset.idx), 1);
          formFileMaps.set(assignmentId, arr);
          renderFileList(form, arr);
        });
      });
    }

    document.querySelectorAll('.submit-form').forEach(form => {
      const assignmentId = form.dataset.assignmentId;
      formFileMaps.set(assignmentId, []);
      const fileInput = form.querySelector('.file-input');

      form.querySelector('.add-files-btn').addEventListener('click', () => fileInput.click());

      fileInput.addEventListener('change', () => {
        const existing = formFileMaps.get(assignmentId) || [];
        for (const f of fileInput.files) {
          const idx = existing.findIndex(e => e.name === f.name);
          if (idx !== -1) existing[idx] = f;
          else if (existing.length < MAX_FILES) existing.push(f);
          else { showToast(`Максимум ${MAX_FILES} файлов`, 'warning'); break; }
        }
        formFileMaps.set(assignmentId, existing);
        renderFileList(form, existing);
        fileInput.value = '';
      });

      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = e.target.querySelector('button[type=submit]');
        const files = formFileMaps.get(assignmentId) || [];
        if (!files.length) { showToast('Выберите файлы для отправки', 'warning'); return; }
        btn.disabled = true;
        const formData = new FormData();
        files.forEach(f => formData.append('files', f));
        try {
          const res = await fetch(`/api/submit/${assignmentId}`, { method: 'POST', headers: getAuthHeaders(), body: formData });
          if (res.status === 401 || res.status === 403) { handleAuthError(); return; }
          if (res.ok) {
            showToast('Работа успешно отправлена!');
            loadAssignments();
          } else {
            const err = await res.json().catch(() => ({ detail: 'Неизвестная ошибка' }));
            showToast('Ошибка: ' + (err.detail || ''), 'danger');
          }
        } catch {
          showToast('Не удалось отправить работу. Проверьте соединение.', 'danger');
        } finally {
          btn.disabled = false;
        }
      });
    });

    document.querySelectorAll('.notebook-send-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const b = e.currentTarget;
        const assignmentId = b.dataset.assignmentId;
        b.disabled = true;
        try {
          const res = await fetch(`/api/submit-notebook/${assignmentId}`, { method: 'POST', headers: getAuthHeaders() });
          if (res.status === 401 || res.status === 403) { handleAuthError(); return; }
          if (res.ok) {
            showToast('Отмечено! Преподаватель получит уведомление.');
            loadAssignments();
          } else {
            const err = await res.json().catch(() => ({ detail: 'Ошибка' }));
            showToast('Ошибка: ' + (err.detail || ''), 'danger');
          }
        } catch {
          showToast('Не удалось отметить отправку. Проверьте соединение.', 'danger');
        } finally {
          b.disabled = false;
        }
      });
    });

    document.querySelectorAll('.download-feedback-file').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const el = e.target.closest('[data-file-id]');
        const fileId = el.dataset.fileId;
        const fileName = el.dataset.fileName;
        try {
          const res = await fetch(`/api/download/feedback-file/${fileId}`, { headers: getAuthHeaders() });
          if (!res.ok) throw new Error('Файл не найден');
          const blob = await res.blob();
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url; a.download = fileName;
          document.body.appendChild(a); a.click();
          window.URL.revokeObjectURL(url); a.remove();
        } catch (err) {
          showToast('Не удалось скачать файл: ' + err.message, 'danger');
        }
      });
    });
  } catch (err) {
    console.error('Ошибка при загрузке заданий:', err);
  }
}
