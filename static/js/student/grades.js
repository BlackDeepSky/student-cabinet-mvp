// Успеваемость студента: загрузка, фильтры по месяцу/году, рендер.
import { escapeHtml } from '../shared/utils.js';
import { getAuthHeaders, handleAuthError } from './api.js';

let gradesData = [];

const GRADES_STATUS_CLS = {
  approved: 'bg-success', rejected: 'bg-danger',
  resubmitted: 'bg-warning text-dark', submitted: 'bg-secondary',
  in_review: 'bg-warning text-dark', notebook_sent: 'bg-info text-dark',
};

function parseGradeDate(str) {
  if (!str || str === '—') return null;
  const parts = str.split(', ')[0].split('.');
  if (parts.length < 3) return null;
  return { month: parseInt(parts[1]), year: parseInt(parts[2]) };
}

function renderGrades(items) {
  const tbody = document.getElementById('grades');
  const emptyEl = document.getElementById('grades-empty');
  tbody.innerHTML = '';
  if (items.length === 0) { emptyEl.classList.remove('d-none'); return; }
  emptyEl.classList.add('d-none');
  items.forEach(g => {
    const cls = GRADES_STATUS_CLS[g.status] || 'bg-secondary';
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${escapeHtml(g.subject)}</td>
      <td>${escapeHtml(g.assignment_title)}</td>
      <td><span class="badge ${cls}">${escapeHtml(g.status_label)}</span></td>
      <td class="d-none d-sm-table-cell" style="font-size:.85rem">${g.submitted_at || '—'}</td>`;
    tbody.appendChild(tr);
  });
}

function applyGradesFilter() {
  const m = parseInt(document.getElementById('grades-filter-month').value) || 0;
  const y = parseInt(document.getElementById('grades-filter-year').value) || 0;
  const filtered = gradesData.filter(g => {
    const d = parseGradeDate(g.submitted_at);
    if (!d) return !m && !y;
    return (!m || d.month === m) && (!y || d.year === y);
  });
  renderGrades(filtered);
}

async function loadGrades() {
  const tbody = document.getElementById('grades');
  tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">Загрузка...</td></tr>';
  document.getElementById('grades-empty').classList.add('d-none');
  try {
    const res = await fetch('/api/grades/me', { headers: getAuthHeaders() });
    if (res.status === 401 || res.status === 403) { handleAuthError(); return; }
    if (!res.ok) throw new Error('Ошибка загрузки');
    gradesData = await res.json();

    const months = [...new Set(gradesData.map(g => parseGradeDate(g.submitted_at)?.month).filter(Boolean))].sort((a,b)=>a-b);
    const years  = [...new Set(gradesData.map(g => parseGradeDate(g.submitted_at)?.year).filter(Boolean))].sort((a,b)=>b-a);
    const MONTH_NAMES = ['','Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'];
    const mSel = document.getElementById('grades-filter-month');
    const ySel = document.getElementById('grades-filter-year');
    mSel.innerHTML = '<option value="">Все месяцы</option>' + months.map(m => `<option value="${m}">${MONTH_NAMES[m]}</option>`).join('');
    ySel.innerHTML = '<option value="">Все годы</option>' + years.map(y => `<option value="${y}">${y}</option>`).join('');

    renderGrades(gradesData);
  } catch (err) {
    tbody.innerHTML = '<tr><td colspan="4" class="text-center text-danger">Ошибка загрузки</td></tr>';
  }
}

document.getElementById('grades-filter-month').addEventListener('change', applyGradesFilter);
document.getElementById('grades-filter-year').addEventListener('change', applyGradesFilter);

document.getElementById('show-grades-btn').addEventListener('click', () => {
  loadGrades();
  bootstrap.Modal.getOrCreateInstance(document.getElementById('gradesModal')).show();
});
