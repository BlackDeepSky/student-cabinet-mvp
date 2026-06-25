// Предметы: список, участники (преподаватели/студенты), зачисление, удаление.
import { escapeHtml, showToast } from '../shared/utils.js';
import { authHeaders, formHeaders } from '../shared/api.js';
import { makePendingList, setupMultiAc } from '../shared/autocomplete.js';
import { state } from './state.js';

let currentSubjectId = null;
let enrolledStudents = [];

export async function loadSubjects() {
  const res = await fetch('/api/admin/subjects', { headers: authHeaders() });
  const subjects = await res.json();
  document.getElementById('subjects-tbody').innerHTML = subjects.map(s => `
    <tr>
      <td>${escapeHtml(s.name)}</td>
      <td>${escapeHtml(s.code || '—')}</td>
      <td>${escapeHtml(s.semester || '—')}</td>
      <td>${escapeHtml(s.teachers || '—')}</td>
      <td class="text-nowrap">
        <button class="btn btn-outline-primary btn-sm me-1" onclick="openMembers(${s.id}, '${escapeHtml(s.name).replace(/'/g, "\\'")}')"><i class="bi bi-people"></i></button>
        <button class="btn btn-outline-danger btn-sm" onclick="deleteSubject(${s.id})"><i class="bi bi-trash"></i></button>
      </td>
    </tr>`).join('');
  const sel = document.getElementById('assignment-subject-select');
  sel.innerHTML = '<option value="">Выберите предмет</option>' + subjects.map(s => `<option value="${s.id}">${escapeHtml(s.name)}</option>`).join('');
}

document.getElementById('add-subject-btn').addEventListener('click', async () => {
  const form = document.getElementById('add-subject-form');
  const err = document.getElementById('add-subject-error');
  err.classList.add('d-none');
  const body = new URLSearchParams(new FormData(form));
  const res = await fetch('/api/admin/subjects', { method: 'POST', headers: formHeaders(), body });
  if (res.ok) {
    bootstrap.Modal.getInstance(document.getElementById('addSubjectModal')).hide(); form.reset(); loadSubjects();
  } else {
    const e = await res.json(); err.textContent = e.detail || 'Ошибка'; err.classList.remove('d-none');
  }
});

async function deleteSubject(id) {
  if (!confirm('Удалить предмет? Все задания предмета также будут удалены.')) return;
  await fetch(`/api/admin/subjects/${id}`, { method: 'DELETE', headers: authHeaders() });
  loadSubjects();
}

const teacherList = makePendingList('teacher', 'assign-teacher-btn');
const studentList = makePendingList('student', 'enroll-student-btn');

setupMultiAc('teacher-autocomplete', 'teacher-ac-list',
  () => state.allTeachers.map(t => ({ value: t.id, label: `${t.last_name} ${t.first_name} (${t.teacher_id})` })),
  teacherList, item => teacherList.add(item));
setupMultiAc('student-autocomplete', 'student-ac-list',
  () => state.allStudents.map(s => ({ value: s.id, label: `${s.last_name} ${s.first_name} (${s.student_id})` })),
  studentList, item => studentList.add(item));

async function openMembers(subjectId, subjectName) {
  currentSubjectId = subjectId;
  document.getElementById('members-subject-name').textContent = subjectName;
  teacherList.clear();
  studentList.clear();
  document.getElementById('teacher-autocomplete').value = '';
  document.getElementById('teacher-ac-list').style.display = 'none';
  document.getElementById('student-autocomplete').value = '';
  document.getElementById('student-ac-list').style.display = 'none';
  const groups = [...new Set(state.allStudents.map(s => s.group_name).filter(Boolean))].sort();
  document.getElementById('enroll-group-select').innerHTML =
    '<option value="" disabled selected>Выберите группу...</option>' +
    groups.map(g => `<option value="${escapeHtml(g)}">${escapeHtml(g)}</option>`).join('');
  await refreshMembers(subjectId);
  new bootstrap.Modal(document.getElementById('membersModal')).show();
}

async function refreshMembers(subjectId) {
  const res = await fetch(`/api/admin/subjects/${subjectId}/members`, { headers: authHeaders() });
  const data = await res.json();
  enrolledStudents = data.students;
  const unenrollAllBtn = document.getElementById('unenroll-all-btn');
  unenrollAllBtn.style.display = enrolledStudents.length ? '' : 'none';
  document.getElementById('members-teachers-list').innerHTML = data.teachers.map(t => `
    <li class="list-group-item d-flex justify-content-between align-items-center py-1">
      ${escapeHtml(t.name)}
      <button class="btn btn-outline-danger btn-sm" onclick="removeTeacher(${t.id})"><i class="bi bi-x"></i></button>
    </li>`).join('') || '<li class="list-group-item text-muted small">Нет преподавателей</li>';
  document.getElementById('members-students-list').innerHTML = data.students.map(s => `
    <li class="list-group-item d-flex justify-content-between align-items-center py-1">
      ${escapeHtml(s.name)}
      <button class="btn btn-outline-danger btn-sm" onclick="unenrollStudent(${s.id})"><i class="bi bi-x"></i></button>
    </li>`).join('') || '<li class="list-group-item text-muted small">Нет студентов</li>';
}

document.getElementById('assign-teacher-btn').addEventListener('click', async () => {
  const ids = teacherList.getValues();
  if (!ids.length) return;
  await Promise.all(ids.map(id =>
    fetch(`/api/admin/subjects/${currentSubjectId}/teachers`, { method: 'POST', headers: formHeaders(), body: new URLSearchParams({ teacher_id: id }) })
  ));
  teacherList.clear();
  document.getElementById('teacher-autocomplete').value = '';
  refreshMembers(currentSubjectId); loadSubjects();
});

document.getElementById('enroll-group-btn').addEventListener('click', () => {
  const group = document.getElementById('enroll-group-select').value;
  if (!group) return;
  const groupStudents = state.allStudents
    .filter(s => s.group_name === group)
    .map(s => ({ value: s.id, label: `${s.last_name} ${s.first_name} (${s.student_id})` }));
  if (!groupStudents.length) { showToast('Нет студентов в группе', 'warning'); return; }
  const added = studentList.addAll(groupStudents);
  const skipped = groupStudents.length - added;
  showToast(
    added ? `Добавлено ${added}${skipped ? `, уже в списке: ${skipped}` : ''}` : `Все ${skipped} уже в списке`,
    added ? 'success' : 'warning'
  );
  document.getElementById('enroll-group-select').value = '';
});

document.getElementById('enroll-student-btn').addEventListener('click', async () => {
  const ids = studentList.getValues();
  if (!ids.length) return;
  await fetch(`/api/admin/subjects/${currentSubjectId}/students/bulk`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ student_ids: ids })
  });
  studentList.clear();
  document.getElementById('student-autocomplete').value = '';
  refreshMembers(currentSubjectId);
});

async function removeTeacher(teacherId) {
  await fetch(`/api/admin/subjects/${currentSubjectId}/teachers/${teacherId}`, { method: 'DELETE', headers: authHeaders() });
  refreshMembers(currentSubjectId); loadSubjects();
}

async function unenrollStudent(studentId) {
  await fetch(`/api/admin/subjects/${currentSubjectId}/students/${studentId}`, { method: 'DELETE', headers: authHeaders() });
  refreshMembers(currentSubjectId);
}

document.getElementById('unenroll-all-btn').addEventListener('click', async () => {
  if (!enrolledStudents.length) return;
  if (!confirm(`Убрать всех ${enrolledStudents.length} студентов с предмета?`)) return;
  await Promise.all(enrolledStudents.map(s =>
    fetch(`/api/admin/subjects/${currentSubjectId}/students/${s.id}`, { method: 'DELETE', headers: authHeaders() })
  ));
  refreshMembers(currentSubjectId);
});

// Вызываются из inline onclick в таблице/списках
window.openMembers = openMembers;
window.deleteSubject = deleteSubject;
window.removeTeacher = removeTeacher;
window.unenrollStudent = unenrollStudent;
