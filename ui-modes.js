/* ============================================================
   NOVEX AI v8.0 — UI MODES CONTROLLER (FULL)
   File: ui-modes.js
   Deps: none
   API:  window.NovexUI
   ============================================================ */

(function () {
  'use strict';

  /* ------------------------------------------------------------
     1. MODE REGISTRY
     ------------------------------------------------------------ */
  const UI_MODES = [
    { id: 'chatgpt',   name: 'ChatGPT',   icon: '💬' },
    { id: 'sidebar',   name: 'Sidebar',   icon: '📚' },
    { id: 'compact',   name: 'Compact',   icon: '🔹' },
    { id: 'zen',       name: 'Zen',       icon: '🧘' },
    { id: 'split',     name: 'Split',     icon: '🧩' },
    { id: 'dashboard', name: 'Dashboard', icon: '📊' },
    { id: 'terminal',  name: 'Terminal',  icon: '⌨️' },
    { id: 'focus',     name: 'Focus',     icon: '🎯' },
    { id: 'mobile',    name: 'Mobile',    icon: '📱' },
    { id: 'floating',  name: 'Floating',  icon: '🪟' }
  ];

  const STORAGE_KEY   = 'novex-ui-mode';
  const AUTO_KEY      = 'novex-ui-auto';
  const DEFAULT_MODE  = 'chatgpt';
  const MOBILE_BP     = 768;

  /* ------------------------------------------------------------
     2. STATE
     ------------------------------------------------------------ */
  let currentMode    = DEFAULT_MODE;
  let autoResponsive = true;
  let userManuallySet = false;

  /* ------------------------------------------------------------
     3. HELPERS
     ------------------------------------------------------------ */
  const $  = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const isValidMode = (id) => UI_MODES.some(m => m.id === id);

  const getStoredMode = () => {
    try { return localStorage.getItem(STORAGE_KEY); }
    catch { return null; }
  };

  const setStoredMode = (id) => {
    try { localStorage.setItem(STORAGE_KEY, id); } catch {}
  };

  const isSmallScreen = () => window.innerWidth < MOBILE_BP;

  /* ------------------------------------------------------------
     4. CORE: APPLY MODE
     ------------------------------------------------------------ */
  function applyMode(id, opts = {}) {
    if (!isValidMode(id)) id = DEFAULT_MODE;

    currentMode = id;
    document.documentElement.dataset.ui = id;

    // Update any picker buttons
    $$('[data-ui-btn]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.uiBtn === id);
    });

    // Close sidebar on mode change (mobile-ish modes)
    if (['zen', 'focus', 'mobile'].includes(id)) {
      closeSidebar();
    }

    // Persist (unless caller says not to)
    if (opts.persist !== false) {
      setStoredMode(id);
      if (opts.userAction) userManuallySet = true;
    }

    // Dispatch event
    document.dispatchEvent(new CustomEvent('novex:ui-changed', {
      detail: { mode: id, userAction: !!opts.userAction }
    }));

    return id;
  }

  /* ------------------------------------------------------------
     5. SIDEBAR (mobile / focus / offcanvas)
     ------------------------------------------------------------ */
  function openSidebar() {
    const sb = $('.sidebar');
    if (!sb) return;
    sb.classList.add('open');
    sb.setAttribute('aria-hidden', 'false');
    document.body.classList.add('sidebar-open');
  }

  function closeSidebar() {
    const sb = $('.sidebar');
    if (!sb) return;
    sb.classList.remove('open');
    sb.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('sidebar-open');
  }

  function toggleSidebar() {
    const sb = $('.sidebar');
    if (!sb) return;
    if (sb.classList.contains('open')) closeSidebar();
    else openSidebar();
  }

  /* ------------------------------------------------------------
     6. KEYBOARD SHORTCUTS
     ------------------------------------------------------------ */
  function bindKeyboard() {
    document.addEventListener('keydown', (e) => {
      const tag = (e.target.tagName || '').toLowerCase();
      const typing = tag === 'input' || tag === 'textarea' || e.target.isContentEditable;

      // Ctrl/Cmd + Shift + U → cycle UI modes
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'u') {
        e.preventDefault();
        cycleMode();
        return;
      }

      // Ctrl/Cmd + B → toggle sidebar
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        toggleSidebar();
        return;
      }

      // Esc → close sidebar / modals
      if (e.key === 'Escape') {
        closeSidebar();
        $$('.modal.open, .settings-modal.open').forEach(m => m.classList.remove('open'));
        return;
      }

      // Numbered modes: Alt + 1..9 → switch
      if (e.altKey && !typing && /^[1-9]$/.test(e.key)) {
        const idx = parseInt(e.key, 10) - 1;
        if (UI_MODES[idx]) {
          e.preventDefault();
          applyMode(UI_MODES[idx].id, { userAction: true });
        }
      }
    });
  }

  /* ------------------------------------------------------------
     7. CYCLE MODES
     ------------------------------------------------------------ */
  function cycleMode() {
    const idx = UI_MODES.findIndex(m => m.id === currentMode);
    const next = UI_MODES[(idx + 1) % UI_MODES.length];
    applyMode(next.id, { userAction: true });
    toast(`${next.icon} UI: ${next.name}`);
  }

  /* ------------------------------------------------------------
     8. AUTO-RESPONSIVE (small screens → mobile mode)
     ------------------------------------------------------------ */
  function bindResponsive() {
    let lastSmall = isSmallScreen();

    const onResize = () => {
      if (!autoResponsive) return;
      const small = isSmallScreen();

      // Enter small screen → force mobile mode (remember previous)
      if (small && !lastSmall) {
        const prev = currentMode;
        sessionStorage.setItem('novex-ui-prev', prev);
        applyMode('mobile', { persist: false });
      }

      // Leave small screen → restore previous mode
      if (!small && lastSmall) {
        const prev = sessionStorage.getItem('novex-ui-prev');
        if (prev && isValidMode(prev)) {
          applyMode(prev, { persist: false });
        } else {
          applyMode(getStoredMode() || DEFAULT_MODE, { persist: false });
        }
      }

      lastSmall = small;
    };

    let raf;
    window.addEventListener('resize', () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(onResize);
    });
  }

  /* ------------------------------------------------------------
     9. CLICK BINDINGS
     ------------------------------------------------------------ */
  function bindClicks() {
    document.addEventListener('click', (e) => {
      // UI picker buttons
      const uiBtn = e.target.closest('[data-ui-btn]');
      if (uiBtn) {
        e.preventDefault();
        applyMode(uiBtn.dataset.uiBtn, { userAction: true });
        return;
      }

      // Sidebar toggle buttons
      const toggleBtn = e.target.closest('[data-toggle-sidebar], .sidebar-toggle, #menuBtn');
      if (toggleBtn) {
        e.preventDefault();
        toggleSidebar();
        return;
      }

      // Click outside sidebar (mobile) → close
      const sb = $('.sidebar');
      if (sb && sb.classList.contains('open')) {
        if (!e.target.closest('.sidebar') && !e.target.closest('[data-toggle-sidebar], .sidebar-toggle, #menuBtn')) {
          closeSidebar();
        }
      }
    });

    // Swipe to close sidebar (mobile)
    let touchX = 0;
    document.addEventListener('touchstart', (e) => {
      touchX = e.touches[0].clientX;
    }, { passive: true });

    document.addEventListener('touchend', (e) => {
      const sb = $('.sidebar');
      if (!sb || !sb.classList.contains('open')) return;
      const dx = e.changedTouches[0].clientX - touchX;
      if (dx < -60) closeSidebar(); // swipe left
    });
  }

  /* ------------------------------------------------------------
     10. RENDER SETTINGS PICKER (if container exists)
     ------------------------------------------------------------ */
  function renderPicker() {
    const containers = $$('[data-ui-picker]');
    if (!containers.length) return;

    containers.forEach(container => {
      container.classList.add('ui-mode-picker');
      container.innerHTML = UI_MODES.map(m => `
        <button type="button" data-ui-btn="${m.id}" title="${m.name} (Alt+${UI_MODES.indexOf(m)+1})">
          ${m.icon} ${m.name}
        </button>
      `).join('');
    });

    // Sync active state
    $$('[data-ui-btn]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.uiBtn === currentMode);
    });
  }

  /* ------------------------------------------------------------
     11. TINY TOAST (optional visual feedback)
     ------------------------------------------------------------ */
  function toast(msg) {
    let el = $('#novex-ui-toast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'novex-ui-toast';
      Object.assign(el.style, {
        position: 'fixed',
        bottom: '24px',
        left: '50%',
        transform: 'translateX(-50%) translateY(20px)',
        background: 'rgba(0,0,0,.85)',
        color: '#fff',
        padding: '10px 16px',
        borderRadius: '12px',
        fontSize: '13px',
        fontWeight: '600',
        zIndex: 99999,
        opacity: '0',
        pointerEvents: 'none',
        transition: 'all .25s ease',
        backdropFilter: 'blur(10px)',
        border: '1px solid rgba(255,255,255,.12)'
      });
      document.body.appendChild(el);
    }
    el.textContent = msg;
    requestAnimationFrame(() => {
      el.style.opacity = '1';
      el.style.transform = 'translateX(-50%) translateY(0)';
    });
    clearTimeout(el._t);
    el._t = setTimeout(() => {
      el.style.opacity = '0';
      el.style.transform = 'translateX(-50%) translateY(20px)';
    }, 1600);
  }

  /* ------------------------------------------------------------
     12. PUBLIC API — window.NovexUI
     ------------------------------------------------------------ */
  window.NovexUI = {
    set:         (id) => applyMode(id, { userAction: true }),
    get:         () => currentMode,
    cycle:       () => cycleMode(),
    list:        () => UI_MODES.slice(),
    openSidebar,
    closeSidebar,
    toggleSidebar,
    setAuto:     (on) => { autoResponsive = !!on; try { localStorage.setItem(AUTO_KEY, on ? '1' : '0'); } catch {} },
    isAuto:      () => autoResponsive,
    reset: () => {
      try { localStorage.removeItem(STORAGE_KEY); } catch {}
      applyMode(DEFAULT_MODE, { userAction: true });
    }
  };

  /* ------------------------------------------------------------
     13. INIT
     ------------------------------------------------------------ */
  function init() {
    // Restore auto setting
    try {
      const a = localStorage.getItem(AUTO_KEY);
      if (a === '0') autoResponsive = false;
    } catch {}

    // Restore mode
    let saved = getStoredMode();
    if (!isValidMode(saved)) saved = DEFAULT_MODE;

    // If small screen on first load → mobile
    if (autoResponsive && isSmallScreen()) {
      saved = 'mobile';
    }

    applyMode(saved, { persist: false });
    renderPicker();
    bindKeyboard();
    bindClicks();
    bindResponsive();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();