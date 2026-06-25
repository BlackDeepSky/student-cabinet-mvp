// Баннер активного объявления.
import { escapeHtml } from '../shared/utils.js';
import { getAuthHeaders } from './api.js';

export async function loadAnnouncement() {
  try {
    const res = await fetch('/api/announcements/active', { headers: getAuthHeaders() });
    if (!res.ok) return;
    const ann = await res.json();
    const banner = document.getElementById('announcement-banner');
    if (!ann) { banner.style.display = 'none'; return; }
    banner.style.display = 'block';
    banner.innerHTML = `
      <div class="announcement-banner">
        <span class="ann-icon"><i class="bi bi-megaphone-fill"></i></span>
        <div>
          <div class="ann-title">${escapeHtml(ann.title)}</div>
          <div class="ann-body">${escapeHtml(ann.body)}</div>
        </div>
        <button class="ann-close" id="ann-close-btn" title="Закрыть"><i class="bi bi-x-lg"></i></button>
      </div>`;
    document.getElementById('ann-close-btn').addEventListener('click', () => {
      banner.style.display = 'none';
    });
  } catch {}
}
