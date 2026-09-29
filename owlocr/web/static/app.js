'use strict';
// Owl OCR main screen logic: header, queue, settings, about; the wizard lives in wizard.js.
// Talks only to the local Flask server; every write carries the X-Owl header (see server.py).
(function () {
  const $ = function (id) { return document.getElementById(id); };
  const t = function (key, vars) { return window.OwlI18n.t(key, vars); };
  const S = {
    settings: null, about: null, status: null, jobs: [], jobsKey: '',
    view: 'queue', dragging: null, wizardShown: false, noticeHidden: '', noticeKey: ''
  };
  const ACTIVE_ENGINE = ['loading', 'ready', 'busy'];

  // ---- helpers -------------------------------------------------------
  async function api(method, path, body) {
    const options = { method: method, headers: { 'X-Owl': '1' } };
    if (body !== undefined) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(body);
    }
    let response;
    try {
      response = await fetch(path, options);
    } catch (e) {                        // never reached the server: the wizard says "no answer"
      throw new Error('network: ' + (e && e.message ? e.message : String(e)));
    }
    let data = null;
    try { data = await response.json(); } catch (e) { data = null; }
    if (!response.ok) {
      const err = new Error((data && data.error) || ('HTTP ' + response.status));
      err.status = response.status;
      throw err;
    }
    return data;
  }

  function toast(message) {
    const el = $('toast');
    el.textContent = message;
    el.classList.add('show');
    clearTimeout(el._timer);
    el._timer = setTimeout(function () { el.classList.remove('show'); }, 2600);
  }

  function confirmDialog(text) {
    const dlg = $('confirmDlg');
    $('confirmText').textContent = text;
    return new Promise(function (resolve) {
      function done(answer) {
        $('confirmYes').removeEventListener('click', yes);
        $('confirmNo').removeEventListener('click', no);
        dlg.removeEventListener('cancel', no);
        if (dlg.open) dlg.close();
        resolve(answer);
      }
      function yes() { done(true); }
      function no() { done(false); }
      $('confirmYes').addEventListener('click', yes);
      $('confirmNo').addEventListener('click', no);
      dlg.addEventListener('cancel', no);
      dlg.showModal();
    });
  }

  function hasBridge() { return !!(window.pywebview && window.pywebview.api); }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function button(labelKey, handler, primary) {
    const b = el('button', primary ? 'primary' : '', t(labelKey));
    b.type = 'button';
    b.addEventListener('click', function (e) { e.stopPropagation(); handler(); });
    return b;
  }

  function showError(err) { toast(t('t_error', { e: err.message || String(err) })); }

  // ---- views, language, theme -----------------------------------------
  function showView(name) {
    S.view = name;
    ['queue', 'review', 'settings', 'about', 'wizard'].forEach(function (v) {
      $('view' + v.charAt(0).toUpperCase() + v.slice(1)).hidden = v !== name;
    });
    document.querySelectorAll('.nav-btn').forEach(function (b) {
      b.classList.toggle('active', b.dataset.view === name);
    });
    if (name === 'settings') renderSettingsForm();
    if (name === 'about') renderAbout();
    if (name === 'wizard') window.OwlWizard.show();
    if (name === 'settings') window.OwlWizard.renderDictionaries($('dictSettings'));
    if (S.status) renderHeader();       // the not-installed notice hides while the wizard is shown
  }

  function applyLanguage(lang) {
    window.OwlI18n.setLang(lang);
    window.OwlI18n.translateDom(document);
    $('langSel').value = window.OwlI18n.getLang();
    renderTheme();
    renderFormats();
    renderHeader();
    S.jobsKey = '';
    renderJobs();
    if (S.view === 'about') renderAbout();
    window.OwlReview.refreshLanguage();
  }

  function currentTheme() {
    return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
  }

  function renderTheme() {
    $('themeBtn').textContent = t(currentTheme() === 'dark' ? 'theme_to_light' : 'theme_to_dark');
  }

  function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem('owl-theme', theme); } catch (e) { /* not stored: fine */ }
    renderTheme();
  }

  // ---- settings --------------------------------------------------------
  async function saveSettings(changes) {
    S.settings = await api('POST', '/api/settings', changes);
    return S.settings;
  }

  function availableFormats() {
    return (S.about && S.about.formats_available) || ['md', 'txt'];
  }

  function chosenFormats() {
    const available = availableFormats();
    const chosen = ((S.settings && S.settings.formats) || ['md']).filter(function (f) {
      return available.indexOf(f) >= 0;
    });
    return chosen.length ? chosen : ['md'];
  }

  function renderFormats() {
    if (!S.settings) return;
    const available = availableFormats();
    document.querySelectorAll('.fmt-box').forEach(function (box) {
      const fmt = box.dataset.fmt;
      const ok = available.indexOf(fmt) >= 0;
      box.checked = ok && S.settings.formats.indexOf(fmt) >= 0;
      box.disabled = !ok;
      box.parentElement.classList.toggle('unavailable', !ok);
      box.parentElement.title = ok ? '' : t('format_unavailable');
    });
  }

  async function onFormatChange(event) {
    const box = event.target;
    const container = box.closest('.formats');
    const formats = Array.from(container.querySelectorAll('.fmt-box'))
      .filter(function (b) { return b.checked && !b.disabled; })
      .map(function (b) { return b.dataset.fmt; });
    if (!formats.length) {
      box.checked = true;
      toast(t('t_need_format'));
      return;
    }
    try {
      await saveSettings({ formats: formats });
    } catch (err) { showError(err); }
    renderFormats();
  }

  function renderMode() {
    if (!S.settings) return;
    document.querySelectorAll('.mode-btn').forEach(function (b) {
      b.classList.toggle('active', b.dataset.mode === S.settings.mode_default);
    });
  }

  function renderSettingsForm() {
    const s = S.settings;
    if (!s) return;
    $('setLanguage').value = s.language_ui;
    $('setMode').value = s.mode_default;
    $('setOutputLocation').value = s.output_location;
    $('setOutputFolder').value = s.output_folder || '';
    $('setTextLayer').value = s.use_text_layer;
    $('setDocLang').value = s.document_language;
    $('setImageLinks').value = s.image_links;
    $('setRepairs').checked = !!s.repairs_enabled;
    $('setSuspicious').checked = !!s.append_suspicious_list;
    $('setFurniture').checked = !!s.keep_page_furniture;
    $('setIdle').value = s.idle_stop_minutes;
    $('setTimeLimit').value = s.time_limit_s;
    $('setDpi').value = s.pdf_dpi;
    $('setWords').value = (s.personal_words || []).join('\n');
    $('settingsError').textContent = '';
    renderFormats();
  }

  async function submitSettings(event) {
    event.preventDefault();
    const changes = {
      language_ui: $('setLanguage').value,
      mode_default: $('setMode').value,
      output_location: $('setOutputLocation').value,
      output_folder: $('setOutputFolder').value.trim(),
      use_text_layer: $('setTextLayer').value,
      document_language: $('setDocLang').value,
      image_links: $('setImageLinks').value,
      repairs_enabled: $('setRepairs').checked,
      append_suspicious_list: $('setSuspicious').checked,
      keep_page_furniture: $('setFurniture').checked,
      idle_stop_minutes: parseInt($('setIdle').value, 10),
      time_limit_s: parseInt($('setTimeLimit').value, 10),
      pdf_dpi: parseInt($('setDpi').value, 10),
      personal_words: $('setWords').value.split('\n').map(function (w) { return w.trim(); })
        .filter(function (w) { return w.length > 0; })
    };
    try {
      await saveSettings(changes);
      $('settingsError').textContent = '';
      applyLanguage(S.settings.language_ui);
      renderMode();
      renderSettingsForm();
      toast(t('t_saved'));
    } catch (err) {
      // No status: the server never answered ("network: ..."), so say it in the user's language.
      // A server failure has no useful text either; a rejected value keeps its own message.
      let text = err.message;
      if (!err.status) text = window.OwlWizard.errorText(err);
      else if (err.status >= 500 || /^HTTP \d+$/.test(err.message || '')) text = t('t_unavailable');
      $('settingsError').textContent = text;
    }
  }

  // ---- header ------------------------------------------------------------
  function engineState() {
    const s = S.status;
    if (!s) return 'stopped';
    return s.installed ? s.engine : 'not_installed';
  }

  function renderHeader() {
    const s = S.status;
    $('btnStart').textContent = t(s && s.paused ? 'btn_resume' : 'btn_start');
    if (!s) return;
    const engine = engineState();
    $('engineState').textContent = t('engine_' + engine);
    $('engineDot').className = 'dot dot-' + engine;
    $('engineVram').textContent = s.vram_used_mib
      ? t('engine_vram', { mib: window.OwlI18n.nfmt(s.vram_used_mib) }) : '';
    $('btnStopEngine').disabled = ACTIVE_ENGINE.indexOf(engine) < 0;
    $('btnStart').disabled = s.running;
    $('btnPause').disabled = !s.running;
    renderNotice(s.error || (s.installed === false && S.view !== 'wizard' ? { code: 'not_installed' } : null));
    renderMode();
    window.OwlMascot.setState(engine, !!s.error);
  }

  function renderNotice(error) {
    const key = error ? JSON.stringify(error) : '';
    S.noticeKey = key;
    if (!error || key === S.noticeHidden) {
      $('notice').hidden = true;
      return;
    }
    $('noticeWizard').hidden = error.code !== 'not_installed';
    if (error.code === 'vram_short') {
      $('noticeText').textContent = t('notice_vram', {
        missing: window.OwlI18n.nfmt(error.missing_mib), need: window.OwlI18n.nfmt(error.need_mib),
        free: window.OwlI18n.nfmt(error.free_mib), mode: t('mode_' + error.mode)
      });
    } else if (error.code === 'not_installed') {
      $('noticeText').textContent = t('notice_not_installed');
    } else if (error.code === 'internal') {
      $('noticeText').textContent = t('notice_internal');
    } else {
      $('noticeText').textContent = t('t_error', { e: error.code || '' });
    }
    $('notice').hidden = false;
  }

  async function stopEngine() {
    const busy = S.status && S.status.current_job;
    if (busy && !(await confirmDialog(t('stop_engine_confirm')))) return;
    try {
      S.status = await api('POST', '/api/engine/stop');
      renderHeader();
      toast(t('t_engine_stopped'));
    } catch (err) { showError(err); }
    refresh();
  }

  // ---- queue -------------------------------------------------------------
  function etaText(seconds) {
    if (seconds < 60) return t('job_eta_short');
    return t('job_eta_min', { n: Math.round(seconds / 60) });
  }

  function renderJobs() {
    const list = $('jobList');
    const jobs = S.jobs;
    list.textContent = '';
    $('emptyQueue').hidden = jobs.length > 0;
    const waiting = jobs.filter(function (j) { return j.state === 'pending' || j.state === 'paused'; }).length;
    const done = jobs.filter(function (j) { return j.state === 'done'; }).length;
    $('queueSummary').textContent = jobs.length ? t('queue_summary', { n: jobs.length, waiting: waiting, done: done }) : '';
    jobs.forEach(function (job) { list.appendChild(jobRow(job)); });
  }

  function metaText(job) {
    const parts = [t('state_' + job.state), t('job_pages', { done: job.pages_done, total: job.pages_total })];
    const current = S.status && S.status.current_job === job.id;
    if (current && S.status.current_page_tokens) parts.push(t('job_tokens', { n: S.status.current_page_tokens }));
    if (job.eta_s !== null && job.eta_s !== undefined) parts.push(etaText(job.eta_s));
    if (job.warnings) parts.push(t('job_warnings', { n: job.warnings }));
    return parts.join(' · ');
  }

  // Only the running row's token count changes every second: update its text in place, so the
  // list is not rebuilt under the pointer (a rebuilt row loses a click, e.g. on Cancel).
  function updateCurrentMeta() {
    const id = S.status && S.status.current_job;
    if (!id) return;
    const job = S.jobs.find(function (j) { return j.id === id; });
    const row = document.querySelector('.job[data-id="' + CSS.escape(id) + '"] .job-meta');
    if (job && row) {
      const text = metaText(job);
      if (row.textContent !== text) row.textContent = text;
    }
  }

  function jobRow(job) {
    const li = el('li', 'job job-' + job.state);
    li.dataset.id = job.id;
    li.draggable = true;
    li.title = t('drag_tip');

    const main = el('div', 'job-main');
    const name = el('div', 'job-name', job.name);
    name.title = job.source;
    const meta = el('div', 'job-meta', metaText(job));
    const bar = el('div', 'bar');
    const fill = el('div', 'fill');
    const pct = job.pages_total ? Math.round(job.pages_done / job.pages_total * 100) : 0;
    fill.style.width = (job.state === 'done' ? 100 : pct) + '%';
    bar.appendChild(fill);
    main.append(name, meta, bar);
    if (job.error) main.appendChild(el('div', 'job-error', job.error));

    const mode = el('select', 'job-mode');
    mode.title = t('job_mode_tip');
    const def = S.settings ? S.settings.mode_default : 'quality';
    [['', t('mode_default_opt', { mode: t('mode_' + def) })],
     ['quality', t('mode_quality')], ['fast', t('mode_fast')]].forEach(function (pair) {
      const option = el('option', '', pair[1]);
      option.value = pair[0];
      mode.appendChild(option);
    });
    mode.value = job.mode || '';
    mode.disabled = job.state === 'running' || job.state === 'done';
    mode.addEventListener('change', async function () {
      try {
        await api('POST', '/api/jobs/' + encodeURIComponent(job.id), { mode: mode.value || null });
      } catch (err) { showError(err); }
      refresh();
    });

    const actions = el('div', 'job-actions');
    const act = function (path, method) {
      return async function () {
        try { await api(method || 'POST', path); } catch (err) { showError(err); }
        refresh();
      };
    };
    const base = '/api/jobs/' + encodeURIComponent(job.id);
    if (job.state === 'running') {
      actions.append(button('btn_cancel', act(base + '/cancel')));
    } else if (job.state === 'pending' || job.state === 'paused') {
      actions.append(button('btn_cancel', act(base + '/cancel')), button('btn_remove', act(base, 'DELETE')));
    } else if (job.state === 'failed' || job.state === 'cancelled') {
      actions.append(button('btn_retry', act(base + '/retry')), button('btn_remove', act(base, 'DELETE')));
    } else if (job.state === 'done') {
      actions.append(button('btn_open_folder', function () { openOutput(job); }));
      if (job.images_dir) actions.append(button('btn_open_images', function () { openPath(job.images_dir); }));
      actions.append(
        button('btn_copy_text', function () { copyText(job); }),
        button('btn_review', function () { window.OwlReview.open(job.id, job.name); }, true),
        button('btn_remove', act(base, 'DELETE')));
    }

    li.append(main, mode, actions);
    li.addEventListener('dragstart', function (e) {
      S.dragging = job.id;
      e.dataTransfer.setData('text/owl-job', job.id);
      e.dataTransfer.effectAllowed = 'move';
      li.classList.add('dragging');
    });
    li.addEventListener('dragend', function () {
      const dropped = S.dragging === null;   // onListDrop already posted the order and refreshed
      S.dragging = null;
      li.classList.remove('dragging');
      if (!dropped) {                        // ended outside the list: show the real order again
        S.jobsKey = '';
        refresh();
      }
    });
    li.addEventListener('dragover', function (e) {
      if (!S.dragging || S.dragging === job.id) return;
      e.preventDefault();
      const dragged = document.querySelector('.job[data-id="' + CSS.escape(S.dragging) + '"]');
      if (!dragged) return;
      const rect = li.getBoundingClientRect();
      const after = e.clientY > rect.top + rect.height / 2;
      li.parentElement.insertBefore(dragged, after ? li.nextSibling : li);
    });
    return li;
  }

  async function onListDrop(e) {
    if (!S.dragging) return;
    e.preventDefault();
    e.stopPropagation();
    const ids = Array.from($('jobList').children).map(function (li) { return li.dataset.id; });
    S.dragging = null;
    try { await api('POST', '/api/jobs/reorder', { ids: ids }); } catch (err) { showError(err); }
    S.jobsKey = '';
    refresh();
  }

  async function addPaths(paths) {
    if (!paths || !paths.length) return;
    try {
      const result = await api('POST', '/api/jobs', { paths: paths });
      toast(t('t_added', { n: result.jobs.length }));
    } catch (err) {
      if (err.status === 400) toast(t('t_no_supported'));
      else showError(err);
    }
    refresh();
  }

  async function addFiles() {
    if (!hasBridge()) { $('pathInput').focus(); toast(t('t_drop_hint')); return; }
    try { addPaths(await window.pywebview.api.pick_files()); } catch (err) { showError(err); }
  }

  async function addFolder() {
    if (!hasBridge()) { $('pathInput').focus(); toast(t('t_drop_hint')); return; }
    try {
      const folder = await window.pywebview.api.pick_folder();
      if (folder) addPaths([folder]);
    } catch (err) { showError(err); }
  }

  function firstOutput(job) {
    const outputs = job.outputs || {};
    return outputs.md || outputs.txt || outputs.docx || outputs.pdf || outputs.owl || null;
  }

  async function openOutput(job) {
    const target = firstOutput(job);
    if (!target || !hasBridge()) return;
    try { await window.pywebview.api.open_folder(target); } catch (err) { showError(err); }
  }

  async function copyText(job) {
    try {
      const result = await api('GET', '/api/jobs/' + encodeURIComponent(job.id) + '/text');
      if (hasBridge()) await window.pywebview.api.copy_text(result.text);
      else await navigator.clipboard.writeText(result.text);
      toast(t('t_copied'));
    } catch (err) { toast(t('t_copy_failed')); }
  }

  // ---- about ---------------------------------------------------------------
  function renderAbout() {
    const a = S.about;
    if (!a) return;
    $('aboutVersion').textContent = a.version;
    $('aboutPython').textContent = a.python;
    $('aboutEngine').textContent = a.engine_id;
    $('aboutRevision').textContent = a.engine_revision;
    $('aboutState').textContent = t('engine_' + engineState());
    $('aboutData').textContent = a.data_root;
    $('aboutLogs').textContent = a.logs_dir;
  }

  async function openPath(path) {
    if (!path || !hasBridge()) return;
    try { await window.pywebview.api.open_folder(path); } catch (err) { showError(err); }
  }

  // ---- polling -------------------------------------------------------------
  function listBusy() {
    const active = document.activeElement;
    return !!(active && active.closest && active.closest('#jobList') && active.tagName === 'SELECT');
  }

  async function refresh() {
    try {
      const both = await Promise.all([api('GET', '/api/status'), api('GET', '/api/jobs')]);
      S.status = both[0];
      S.jobs = both[1].jobs;
      renderHeader();
      const key = JSON.stringify([S.jobs, S.status.current_job]);
      if (key !== S.jobsKey && !S.dragging && !listBusy()) {
        S.jobsKey = key;
        renderJobs();
      } else if (!S.dragging) {
        updateCurrentMeta();
      }
      if (!S.status.installed && !S.wizardShown) {
        S.wizardShown = true;
        showView('wizard');
      }
    } catch (err) { /* the server may be busy; the next poll tries again */ }
  }

  function poll() {
    refresh().finally(function () { setTimeout(poll, 1000); });
  }

  // ---- wiring --------------------------------------------------------------
  function wire() {
    document.querySelectorAll('.nav-btn').forEach(function (b) {
      b.addEventListener('click', function () { showView(b.dataset.view); });
    });
    $('langSel').addEventListener('change', async function () {
      const lang = $('langSel').value;
      applyLanguage(lang);
      try { await saveSettings({ language_ui: lang }); } catch (err) { showError(err); }
    });
    $('themeBtn').addEventListener('click', function () {
      setTheme(currentTheme() === 'dark' ? 'light' : 'dark');
    });
    document.querySelectorAll('.mode-btn').forEach(function (b) {
      b.addEventListener('click', async function () {
        try { await saveSettings({ mode_default: b.dataset.mode }); } catch (err) { showError(err); }
        renderMode();
        S.jobsKey = '';
        renderJobs();
      });
    });
    $('btnStopEngine').addEventListener('click', stopEngine);
    $('noticeClose').addEventListener('click', function () {
      S.noticeHidden = S.noticeKey || '';
      $('notice').hidden = true;
    });
    $('btnAddFiles').addEventListener('click', addFiles);
    $('btnAddFolder').addEventListener('click', addFolder);
    $('pathForm').addEventListener('submit', function (e) {
      e.preventDefault();
      const value = $('pathInput').value.trim();
      if (!value) return;
      $('pathInput').value = '';
      addPaths([value]);
    });
    document.querySelectorAll('.fmt-box').forEach(function (box) {
      box.addEventListener('change', onFormatChange);
    });
    $('btnStart').addEventListener('click', async function () {
      S.noticeHidden = '';
      try { S.status = await api('POST', '/api/run/start'); } catch (err) { showError(err); }
      refresh();
    });
    $('btnPause').addEventListener('click', async function () {
      try { S.status = await api('POST', '/api/run/pause'); } catch (err) { showError(err); }
      refresh();
    });
    $('btnClear').addEventListener('click', async function () {
      try { await api('POST', '/api/jobs/clear'); } catch (err) { showError(err); }
      refresh();
    });
    $('jobList').addEventListener('drop', onListDrop);
    $('jobList').addEventListener('dragover', function (e) { if (S.dragging) e.preventDefault(); });

    // Files dropped anywhere. Without preventDefault the window would open the file instead.
    // In the app window Python receives the full paths (see __main__._run_window); a browser
    // never reveals paths, so there the user is pointed to the buttons. The page never POSTs the
    // dropped files itself (Python already added them). The listeners sit on `document`, the node
    // pywebview's own drop handler uses: it stops propagation there, so `window` would never
    // hear the drop and the highlight would stay on.
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(function (type) {
      document.addEventListener(type, function (e) { if (!S.dragging) e.preventDefault(); });
    });
    document.addEventListener('dragover', function () { if (!S.dragging) $('drop').classList.add('over'); });
    document.addEventListener('dragleave', function (e) { if (!e.relatedTarget) $('drop').classList.remove('over'); });
    document.addEventListener('drop', function () {
      $('drop').classList.remove('over');
      if (S.dragging) return;
      if (hasBridge()) setTimeout(refresh, 700);
      else toast(t('t_drop_hint'));
    });

    $('settingsForm').addEventListener('submit', submitSettings);
    $('btnBrowseOut').addEventListener('click', async function () {
      if (!hasBridge()) return;
      try {
        const folder = await window.pywebview.api.pick_folder();
        if (folder) {
          $('setOutputFolder').value = folder;
          $('setOutputLocation').value = 'folder';
        }
      } catch (err) { showError(err); }
    });
    $('btnVerify').addEventListener('click', function () { window.OwlWizard.verify(); });
    $('btnRemoveEngine').addEventListener('click', function () { window.OwlWizard.remove(); });
    $('btnReinstall').addEventListener('click', function () { window.OwlWizard.reinstall(); });
    $('btnMove').addEventListener('click', function () { window.OwlWizard.move(); });
    $('noticeWizard').addEventListener('click', function () { showView('wizard'); });
    $('btnOpenLogs').addEventListener('click', function () { openPath(S.about && S.about.logs_dir); });
    $('btnOpenData').addEventListener('click', function () { openPath(S.about && S.about.data_root); });
  }

  async function start() {
    let theme = null;
    try { theme = localStorage.getItem('owl-theme'); } catch (e) { theme = null; }
    if (theme !== 'dark' && theme !== 'light') {
      theme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    document.documentElement.setAttribute('data-theme', theme);
    window.OwlMascot.init($('owl'), function () { toast(t('owl_hoot')); });
    window.OwlReview.init({
      api: api, toast: toast, showView: showView, getFormats: chosenFormats,
      isRunning: function (id) { return !!(S.status && S.status.current_job === id); }
    });
    window.OwlWizard.init({ api: api, toast: toast, confirmDialog: confirmDialog, showView: showView });
    wire();
    try {
      const loaded = await Promise.all([api('GET', '/api/settings'), api('GET', '/api/about')]);
      S.settings = loaded[0];
      S.about = loaded[1];
    } catch (err) { showError(err); }
    applyLanguage((S.settings && S.settings.language_ui) || 'cs');
    showView('queue');
    poll();
  }

  start();
})();
