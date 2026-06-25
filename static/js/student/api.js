// Авторизация студента, бейдж приложения, переключение экранов.
import { showToast } from '../shared/utils.js';

const TOKEN_KEY = 'student_token';
const NAME_KEY = 'student_name';

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const getName = () => localStorage.getItem(NAME_KEY);

export function setSession(token, name) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(NAME_KEY, name);
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(NAME_KEY);
}

export function getAuthHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function showLogin() {
  document.getElementById('app-navbar').style.display = 'none';
  document.getElementById('login-section').style.display = 'flex';
  document.getElementById('main-section').style.display = 'none';
}

export function showMain() {
  document.getElementById('app-navbar').style.display = 'flex';
  document.getElementById('login-section').style.display = 'none';
  document.getElementById('main-section').style.display = 'block';
}

export function handleAuthError() {
  showToast('Сессия истекла — войдите снова', 'warning');
  clearSession();
  showLogin();
}

export async function updateBadge() {
  const token = getToken();
  if (!token) return;
  try {
    const res = await fetch('/api/badge', { headers: { 'Authorization': `Bearer ${token}` } });
    if (!res.ok) return;
    const { count } = await res.json();
    if ('setAppBadge' in navigator) {
      count > 0 ? navigator.setAppBadge(count) : navigator.clearAppBadge();
    }
    document.title = count > 0 ? `(${count}) Кабинет студента` : 'Кабинет студента';
  } catch {}
}

setInterval(updateBadge, 60000);
