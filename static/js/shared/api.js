// Работа с токеном, заголовки авторизации и скачивание CSV.

const TOKEN_KEY = 'admin_token';

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

export const authHeaders = () => ({ 'Authorization': `Bearer ${getToken()}` });
export const formHeaders = () => ({
  'Authorization': `Bearer ${getToken()}`,
  'Content-Type': 'application/x-www-form-urlencoded',
});

export async function downloadCSV(url, filename) {
  const res = await fetch(url, { headers: authHeaders() });
  if (!res.ok) return;
  const blob = await res.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

// Вызывается из inline onclick в разметке
window.downloadCSV = downloadCSV;
