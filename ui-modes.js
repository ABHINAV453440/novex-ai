/* ============================================================
   NOVEX AI — UI Modes Controller v1.0
   ============================================================ */

(function(){
  'use strict';

  /* ============ UI MODE DEFINITIONS ============ */
  const UI_MODES = [
    {
      id: 'classic',
      icon: '💬',
      name: 'Classic',
      desc: 'Default balanced layout',
      shortcut: '1'
    },
    {
      id: 'compact',
      icon: '📱',
      name: 'Compact',
      desc: 'Smaller, more visible',
      shortcut: '2'
    },
    {
      id: 'zen',
      icon: '🧘',
      name: 'Zen',
      desc: 'Minimal, calm, focused',
      shortcut: '3'
    },
    {
      id: 'focus',
      icon: '🎯',
      name: 'Focus',
      desc: 'Only chat — no chrome',
      shortcut: '4'
    },
    {
      id: 'dual',
      icon: '🔀',
      name: 'Dual Panel',
      desc: 'Chat + side panel',
      shortcut: '5'
    }
  ];

  const ALL_UI_CLASSES = UI_MODES.map(m => 'ui-' + m.id);
  const STORAGE_KEY = 'novex-ui-mode';

  /* ============ APPLY UI MODE ============ */
  window.setUIMode = function(mode){
    if(!UI_MODES.find(m => m.id === mode)) mode = 'classic';

    // Remove all ui-* classes
    document.body.classList.remove(...ALL_UI_CLASSES);

    // Add current one (classic is default = no class needed, but we add for consistency)
    if(mode !== 'classic'){
      document.body.classList.add('ui-' + mode);
    }

    // Save to localStorage
    try{ localStorage.setItem(STORAGE_KEY, mode); }catch(e){}

    // Update picker active state
    const picker = document.getElementById('uiModePicker');
    if(picker){
      picker.querySelectorAll('.ui-mode-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.mode === mode);
      });
    }

    // Handle dual panel creation/removal
    if(mode === 'dual'){
      ensureDualPanel();
    } else {
      const panel = document.querySelector('.dual-panel');
      if(panel) panel.remove();
    }

    // Show toast (only if user initiated, not on load)
    if(!window._uiModeInitializing){
      const m = UI_MODES.find(m => m.id === mode);
      if(typeof toast === 'function') toast(`✓ UI: ${m.icon} ${m.name}`);
    }

    // Trigger resize for layout recalcs
    window.dispatchEvent(new Event('resize'));
  };

  /* ============ DUAL PANEL ============ */
  function ensureDualPanel(){
    if(document.querySelector('.dual-panel')) return;
    const main = document.querySelector('.main');
    if(!main) return;

    const panel = document.createElement('aside');
    panel.className = 'dual-panel';
    panel.innerHTML = `
      <div class="dual-panel-head">
        <span>📌 Quick Panel</span>
        <button onclick="refreshDualPanel()" style="background:none;border:none;color:var(--mut);cursor:pointer;font-size:.9rem" title="Refresh">↻</button>
      </div>
      <div class="dual-card">
        <h4>🎯 Quick Quiz</h4>
        <p>15 categories, streak bonus, XP multiplier</p>
        <button class="btn" onclick="openQuiz()">Start Quiz →</button>
      </div>
      <div class="dual-card">
        <h4>🔍 Real-time Search</h4>
        <p>Serper + DDGS live web search</p>
        <button class="btn" onclick="openSearchPanel()">Search →</button>
      </div>
      <div class="dual-card">
        <h4>📚 Flashcards + SRS</h4>
        <p>Spaced repetition review</p>
        <button class="btn" onclick="openSRS()">Review Now →</button>
      </div>
      <div class="dual-card">
        <h4>🎙️ Voice Assistant</h4>
        <p>Talk to NOVEX hands-free</p>
        <button class="btn" onclick="toggleVoiceAssistant()">Start Voice →</button>
      </div>
      <div class="dual-card" id="dualRecentCard">
        <h4>🕐 Recent Chats</h4>
        <div id="dualRecentList" style="font-size:.72rem;color:var(--dim)">Loading…</div>
      </div>
      <div class="dual-card" id="dualStatsCard">
        <h4>📊 Your Progress</h4>
        <div id="dualStatsList" style="font-size:.72rem;color:var(--dim)">Loading…</div>
      </div>
    `;
    main.appendChild(panel);
    loadDualPanelData();
  }

  window.refreshDualPanel = function(){
    loadDualPanelData();
    if(typeof toast === 'function') toast('✓ Refreshed');
  };

  async function loadDualPanelData(){
    // Recent chats
    try{
      const r = await fetch('/chats');
      if(r.ok){
        const chats = await r.json();
        const list = document.getElementById('dualRecentList');
        if(list){
          const recent = (chats || []).slice(0, 4);
          list.innerHTML = recent.length
            ? recent.map(c => `<a href="javascript:void(0)" onclick="loadChat('${c.id}')" style="display:block;padding:.35rem 0;color:var(--cy);text-decoration:none;font-size:.75rem;border-bottom:1px solid var(--bor);overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escapeAttr(c.title||'')}">${escapeHtml((c.title||'').slice(0,40))}</a>`).join('')
            : '<em>No chats yet</em>';
        }
      }
    }catch(e){}

    // Stats
    try{
      const r = await fetch('/gamification/profile');
      if(r.ok){
        const d = await r.json();
        const list = document.getElementById('dualStatsList');
        if(list){
          list.innerHTML = `
            <div style="line-height:1.7">
              <div>${d.level_icon||'🌱'} <strong style="color:var(--txt)">${d.level||'Beginner'}</strong></div>
              <div style="color:var(--dim);font-size:.7rem">${d.exp||0} EXP · ${d.unlocked_count||0}/${d.total_badges||0} badges</div>
              <div style="color:var(--dim);font-size:.7rem;margin-top:.3rem">🎯 ${(d.stats?.quiz_count||0)} quizzes · 📚 ${(d.stats?.flashcards_reviewed||0)} cards</div>
            </div>
          `;
        }
      }
    }catch(e){}
  }

  function escapeHtml(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
  function escapeAttr(s){return escapeHtml(s).replace(/"/g,'&quot;')}

  /* ============ UI MODE PICKER ============ */
  function buildUIModePicker(){
    if(document.getElementById('uiModePicker')) return;

    const picker = document.createElement('div');
    picker.className = 'ui-mode-picker';
    picker.id = 'uiModePicker';

    const current = localStorage.getItem(STORAGE_KEY) || 'classic';

    let html = `<div class="ui-mode-picker-label">🖥️ UI Layout Mode</div>`;
    UI_MODES.forEach(m => {
      html += `
        <button class="ui-mode-btn ${m.id===current?'active':''}" data-mode="${m.id}"
                onclick="setUIMode('${m.id}');closeUIModePicker()">
          <span class="uic-icon">${m.icon}</span>
          <div class="uic-body">
            <div class="uic-name">${m.name}</div>
            <div class="uic-desc">${m.desc}</div>
          </div>
          <span class="uic-check">✓</span>
        </button>
      `;
    });
    html += `<div style="font-size:.65rem;color:var(--mut);padding:.5rem .6rem;border-top:1px solid var(--bor);margin-top:.3rem">Shortcut: <kbd style="background:var(--sur3);padding:1px 4px;border-radius:3px">⌘/</kbd> → 1-5</div>`;
    picker.innerHTML = html;

    document.body.appendChild(picker);
  }

  window.openUIModePicker = function(){
    buildUIModePicker();
    const p = document.getElementById('uiModePicker');
    if(p) p.classList.toggle('open');
  };

  window.closeUIModePicker = function(){
    const p = document.getElementById('uiModePicker');
    if(p) p.classList.remove('open');
  };

  /* ============ KEYBOARD SHORTCUTS ============ */
  document.addEventListener('keydown', e => {
    // ⌘/ or Ctrl+/ → open picker
    if((e.metaKey || e.ctrlKey) && e.key === '/'){
      e.preventDefault();
      window.openUIModePicker();
      return;
    }

    // Escape → close picker
    if(e.key === 'Escape'){
      window.closeUIModePicker();
    }

    // When picker is open: 1-5 → select mode
    const picker = document.getElementById('uiModePicker');
    if(picker && picker.classList.contains('open')){
      const idx = parseInt(e.key);
      if(idx >= 1 && idx <= 5){
        e.preventDefault();
        window.setUIMode(UI_MODES[idx-1].id);
        window.closeUIModePicker();
      }
    }
  });

  /* ============ CLICK OUTSIDE → CLOSE PICKER ============ */
  document.addEventListener('click', e => {
    const picker = document.getElementById('uiModePicker');
    if(!picker) return;
    if(!e.target.closest('#uiModePicker') && !e.target.closest('[onclick*="openUIModePicker"]')){
      picker.classList.remove('open');
    }
  });

  /* ============ INIT ON LOAD ============ */
  function init(){
    window._uiModeInitializing = true;
    const saved = localStorage.getItem(STORAGE_KEY) || 'classic';
    window.setUIMode(saved);
    setTimeout(() => { window._uiModeInitializing = false; }, 500);
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  /* ============ EXPORT FOR DEBUG ============ */
  window.UI_MODES = UI_MODES;
  console.log('✓ UI Modes loaded:', UI_MODES.map(m => m.id).join(', '));

})();