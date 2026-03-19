/* ─── App.js — RITB Shared JS ─── */

// This automatically detects if you are running it locally or on Vercel
const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' || window.location.protocol === 'file:';

// Use relative URLs to work on any server (local or deployed)
const API = isLocal
  ? 'http://localhost:5000'
  : 'https://hospitable-smile-production-05b4.up.railway.app';  // Empty string = same origin

const SERVER = isLocal
  ? 'http://localhost:5000'
  : 'https://hospitable-smile-production-05b4.up.railway.app';  // Empty string = same origin for navigation

// ─── If opened directly via file://, show message or try localhost ───
(function () {
  if (window.location.protocol === 'file:') {
    console.warn('Opening HTML files directly may not work correctly. Please serve these files through a web server.');
  }
})();

// ─── Navigate helper: always navigate via standard relative routing ───
function goTo(page) {
  window.location.href = '/' + page;
}

// ─── Toast Notifications ───
function showToast(message, type = 'default', duration = 3500) {
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = message;
  document.body.appendChild(t);
  setTimeout(() => { t.style.animation = 'none'; t.style.opacity = '0'; setTimeout(() => t.remove(), 300); }, duration);
}

// ─── Auth State ───
let currentUser = null;

async function loadAuthState() {
  const token = localStorage.getItem('token');
  if (!token) {
    currentUser = null;
    renderNavAuth();
    return;
  }
  try {
    // using apiFetch which automatically attaches the token
    currentUser = await apiFetch('/api/auth/me');
  } catch {
    currentUser = null;
    localStorage.removeItem('token');
  }
  renderNavAuth();
}

function renderNavAuth() {
  const actions = document.getElementById('nav-actions');
  // Remove any previously injected mobile auth link
  const existingMobileAuth = document.getElementById('mobile-auth-link');
  if (existingMobileAuth) existingMobileAuth.remove();

  if (!actions) return;
  if (currentUser) {
    const role = currentUser.role;
    const dashLink = role === 'admin' ? 'admin.html' : role === 'teacher' ? 'teacher-dashboard.html' : null;
    actions.innerHTML = `
      ${dashLink ? `<a href="${dashLink}" class="btn btn-secondary btn-sm btn-pill" style="font-weight:700">${role === 'admin' ? '⚙ Admin' : '📊 Dashboard'}</a>` : ''}
      <a href="${dashLink || 'index.html'}" class="user-chip">
        <span class="material-symbols-rounded" style="font-size:1.1rem">account_circle</span>
        ${currentUser.name.split(' ')[0]}
      </a>
      <button class="btn btn-secondary btn-sm btn-pill" onclick="logout()">Sign Out</button>`;

    // Inject into mobile dropdown too
    const navLinks = document.getElementById('nav-links');
    if (navLinks) {
      const mobileAuth = document.createElement('div');
      mobileAuth.id = 'mobile-auth-link';
      mobileAuth.style.cssText = 'display:flex;gap:.5rem;flex-wrap:wrap;padding:.5rem .5rem 0;border-top:1px solid var(--surface-container);margin-top:.25rem';
      mobileAuth.innerHTML = `
        ${dashLink ? `<a href="${dashLink}" class="btn btn-secondary btn-sm btn-pill" style="font-weight:700;flex:1;justify-content:center">${role === 'admin' ? '⚙ Admin' : '📊 Dashboard'}</a>` : ''}
        <button class="btn btn-secondary btn-sm btn-pill" style="flex:1" onclick="logout()">Sign Out</button>`;
      navLinks.appendChild(mobileAuth);
    }
  } else {
    actions.innerHTML = `<a href="login.html" class="btn-nav-login">Sign In</a>`;

    // Inject Sign In into mobile dropdown
    const navLinks = document.getElementById('nav-links');
    if (navLinks) {
      const mobileAuth = document.createElement('a');
      mobileAuth.id = 'mobile-auth-link';
      mobileAuth.href = 'login.html';
      mobileAuth.className = 'btn-nav-login';
      mobileAuth.style.cssText = 'margin-top:.5rem;text-align:center;border-top:1px solid var(--surface-container);padding-top:.75rem';
      mobileAuth.textContent = 'Sign In';
      navLinks.appendChild(mobileAuth);
    }
  }
}


async function logout() {
  try { await apiFetch('/api/auth/logout', { method: 'POST' }); } catch (e) { }
  localStorage.removeItem('token');
  currentUser = null;
  renderNavAuth();
  showToast('Signed out successfully');
  setTimeout(() => goTo('index.html'), 800);
}

// ─── API Helpers ───
async function apiFetch(url, options = {}) {
  const token = localStorage.getItem('token');
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const combinedHeaders = { ...headers, ...(options.headers || {}) };
  const response = await fetch(`${API}${url}`, { ...options, headers: combinedHeaders });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);

  // Auto-save token if the server returned a new one (e.g. login/register)
  if (data.token) {
    localStorage.setItem('token', data.token);
  }

  return data;
}

// ─── Format Helpers ───
function formatDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr.includes('T') ? dateStr : dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
}

function formatDateShort(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr.includes('T') ? dateStr : dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatTime(timeStr) {
  if (!timeStr) return '';
  const [h, m] = timeStr.split(':').map(Number);
  const period = h >= 12 ? 'PM' : 'AM';
  const hour = h % 12 || 12;
  return `${hour}:${String(m).padStart(2, '0')} ${period}`;
}

function timeAgo(dateStr) {
  const d = new Date(dateStr);
  const diff = Date.now() - d.getTime();
  const days = Math.floor(diff / 86400000);
  if (days === 0) {
    const hours = Math.floor(diff / 3600000);
    if (hours === 0) return 'Just now';
    return `${hours}h ago`;
  }
  if (days < 7) return `${days}d ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  return formatDate(dateStr);
}

function getCategoryColor(cat) {
  const map = {
    'Academic': 'chip-primary', 'Academics': 'chip-primary',
    'Athletics': 'chip-tertiary', 'Sports': 'chip-tertiary',
    'Research': 'chip-secondary', 'Social': 'chip-warning',
    'Career': 'chip-success', 'Arts': 'chip-tertiary',
    'General': 'chip-primary'
  };
  return map[cat] || 'chip-primary';
}

// ─── Image Fallback ───
function imgFallback(img, type = 'news') {
  const fallbacks = {
    news: 'https://images.unsplash.com/photo-1562774053-701939374585?w=800',
    event: 'https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=800',
    faculty: 'https://i.pravatar.cc/300?img=1'
  };
  img.src = fallbacks[type] || fallbacks.news;
  img.onerror = null;
}

// ─── Active Nav Link ───
function setActiveNav() {
  const path = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-links a').forEach(a => {
    const href = a.getAttribute('href');
    if (href === path || (path === '' && href === 'index.html')) a.classList.add('active');
  });
}

// ─── Mobile Menu Toggle ───
function toggleMenu() {
  const links = document.getElementById('nav-links');
  if (links) links.classList.toggle('active');
}

// ─── Init on Page Load ───
document.addEventListener('DOMContentLoaded', () => {
  loadAuthState();
  setActiveNav();
});
