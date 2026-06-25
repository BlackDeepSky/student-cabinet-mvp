// Мультивыбор с «чипами» и выпадающим автокомплитом.
import { escapeHtml } from './utils.js';

export function makePendingList(prefix, actionBtnId) {
  const items = [];
  const pendingEl = document.getElementById(prefix + '-pending');
  const chipsEl   = document.getElementById(prefix + '-pending-chips');
  const actionBtn = actionBtnId ? document.getElementById(actionBtnId) : null;
  function render() {
    pendingEl.style.display = items.length ? '' : 'none';
    if (actionBtn) actionBtn.disabled = !items.length;
    chipsEl.innerHTML = items.map((item, i) => {
      const name = item.label.split('(')[0].trim();
      return `<span class="badge rounded-pill text-bg-success d-inline-flex align-items-center gap-1 px-2 py-1" style="font-size:.75rem;font-weight:500;">${escapeHtml(name)}<button class="btn-close btn-close-white remove-chip" style="font-size:.45rem;" data-idx="${i}"></button></span>`;
    }).join('');
    chipsEl.querySelectorAll('.remove-chip').forEach(btn => {
      btn.addEventListener('click', () => { items.splice(parseInt(btn.dataset.idx), 1); render(); });
    });
  }
  document.getElementById(prefix + '-pending-clear').addEventListener('click', () => { items.length = 0; render(); });
  return {
    add(item) {
      if (!items.some(i => String(i.value) === String(item.value))) { items.push(item); render(); return true; }
      return false;
    },
    addAll(newItems) {
      let added = 0;
      newItems.forEach(item => {
        if (!items.some(i => String(i.value) === String(item.value))) { items.push(item); added++; }
      });
      if (added) render();
      return added;
    },
    getValues() { return items.map(i => i.value); },
    clear() { items.length = 0; render(); },
    has(value) { return items.some(i => String(i.value) === String(value)); }
  };
}

export function setupMultiAc(inputId, listId, getData, pending, onAdd) {
  const input = document.getElementById(inputId);
  const list  = document.getElementById(listId);
  input.addEventListener('input', () => {
    const q = input.value.toLowerCase().trim();
    list.innerHTML = '';
    if (!q) { list.style.display = 'none'; return; }
    const hits = getData().filter(d => !pending.has(d.value) && d.label.toLowerCase().includes(q)).slice(0, 8);
    if (!hits.length) { list.style.display = 'none'; return; }
    hits.forEach(item => {
      const div = document.createElement('div');
      div.className = 'ac-item';
      div.textContent = item.label;
      div.addEventListener('mousedown', e => { e.preventDefault(); input.value = ''; list.style.display = 'none'; onAdd(item); });
      list.appendChild(div);
    });
    list.style.display = 'block';
  });
  input.addEventListener('blur', () => setTimeout(() => { list.style.display = 'none'; }, 150));
}
