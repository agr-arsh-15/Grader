/* app.js — Frontend Controller: Grade triggers, Clipboard, Modals, Toasts */

document.addEventListener('DOMContentLoaded', () => {
  // ── Grade button trigger ──────────────────────────────────────────
  document.querySelectorAll('.btn-grade').forEach(btn => {
    btn.addEventListener('click', async () => {
      const submissionId = btn.dataset.submissionId;
      if (!submissionId) return;

      const confirmed = confirm('Trigger automated tests and AI rubric grading for this submission? This may take up to 60 seconds.');
      if (!confirmed) return;

      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span> Grading…';

      try {
        const resp = await fetch(`/api/admin/submissions/${submissionId}/grade`, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
        });
        const data = await resp.json();

        if (resp.ok) {
          showToast('Grading pipeline finished! Refreshing scorecard…', 'success');
          setTimeout(() => location.reload(), 1200);
        } else {
          showToast(data.detail || 'Grading encountered an issue. Check server logs.', 'error');
          btn.disabled = false;
          btn.innerHTML = '⚡ Grade';
        }
      } catch (err) {
        showToast('Network error while grading: ' + err.message, 'error');
        btn.disabled = false;
        btn.innerHTML = '⚡ Grade';
      }
    });
  });

  // ── Candidate multi-select toggle all ──────────────────────────
  const toggleAll = document.getElementById('toggle-all-candidates');
  if (toggleAll) {
    toggleAll.addEventListener('change', () => {
      document.querySelectorAll('.candidate-checkbox').forEach(cb => {
        cb.checked = toggleAll.checked;
      });
      if (typeof updateSelectedCounter === 'function') {
        updateSelectedCounter();
      }
    });
  }

  // ── Modal ESC and backdrop dismiss ─────────────────────────────
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal-backdrop').forEach(m => {
        m.style.display = 'none';
      });
    }
  });

  document.querySelectorAll('.modal-backdrop').forEach(modal => {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        modal.style.display = 'none';
      }
    });
  });
});

// ── Clipboard Copy Helper ─────────────────────────────────────────
async function copyText(text, successMessage = 'Copied to clipboard!') {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.left = '-999999px';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      document.execCommand('copy');
      textArea.remove();
    }
    showToast(successMessage, 'success');
  } catch (err) {
    showToast('Failed to copy: ' + err.message, 'error');
  }
}

// ── Toast Notification System ─────────────────────────────────────
function showToast(message, type = 'info') {
  const container = getOrCreateToastContainer();
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  
  const icon = type === 'success' ? '✅ ' : (type === 'error' ? '❌ ' : 'ℹ️ ');
  toast.textContent = icon + message;
  
  container.appendChild(toast);

  requestAnimationFrame(() => {
    toast.classList.add('toast-visible');
  });

  setTimeout(() => {
    toast.classList.remove('toast-visible');
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function getOrCreateToastContainer() {
  let c = document.getElementById('toast-container');
  if (!c) {
    c = document.createElement('div');
    c.id = 'toast-container';
    document.body.appendChild(c);
  }
  return c;
}
