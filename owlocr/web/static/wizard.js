'use strict';
// Owl OCR setup wizard (design 6.1, plus the optional dictionary step), the Settings actions
// Reinstall and Move (design 10.3) and the Settings section for the spell-check dictionaries.
// Renders into <section id="viewWizard">. app.js calls OwlWizard.init({...}) with its own api()
// helper (which sends the X-Owl header), toast(), confirmDialog() and showView(); showView('wizard')
// calls OwlWizard.show(). Text comes from wizard_i18n.js through window.OwlI18n.t; dynamic values
// are inserted with textContent only.
(function () {
  const STEPS = ['welcome', 'hardware', 'location', 'install', 'selftest', 'dicts', 'done'];
  const STAGES = ['tools', 'python', 'venv', 'torch', 'deps', 'model', 'worker', 'patch', 'selftest', 'mark'];
  const POLL_MS = 1000;
  const MODEL_BYTES = 7516192768;      // 7 GiB: space no longer needed once the model is present

  const W = {
    deps: null, root: null, step: 'welcome', probe: null, progress: null, timer: null,
    busy: '', notice: null, nextNotice: null, speed: { stage: null, bytes: 0, time: 0, rate: 0 },
    dicts: null, dictChoice: { cs: true, en: true }, dictTimer: null, dictPanel: null, engineBusy: false, copy: false, dictStarting: false
  };
  const ENGINE_BUTTONS = ['btnVerify', 'btnReinstall', 'btnMove', 'btnRemoveEngine'];

  function t(key, vars) { return window.OwlI18n.t(key, vars); }
  function lang() { return window.OwlI18n.getLang(); }
  function locale() { return lang() === 'cs' ? 'cs-CZ' : 'en-US'; }

  function h(tag, attrs) {
    const node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (name) {
      const value = attrs[name];
      if (name === 'onclick') node.addEventListener('click', value);
      else if (name === 'text') node.textContent = value;
      else if (name === 'disabled' || name === 'checked') node[name] = !!value;
      else if (value !== null && value !== undefined) node.setAttribute(name, value);
    });
    Array.prototype.slice.call(arguments, 2).forEach(function (child) {
      if (child === null || child === undefined || child === false) return;
      node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
    });
    return node;
  }

  function api(method, path, body) { return W.deps.api(method, path, body); }

  function errorKey(message) {
    const code = String(message || 'unknown').split(':')[0].trim();
    const key = 'wz_error_' + code;
    return t(key) === key ? 'wz_error_unknown' : key;
  }

  function detailOf(message) {
    const text = String(message || '');
    const at = text.indexOf(':');
    return at >= 0 ? text.slice(at + 1).trim() : '';
  }

  // app.js's api() turns a fetch that never reached the server into "network: ...", so it maps to
  // wz_error_network like any other code; unknown codes fall back to the generic message.
  function keyOfError(err) {
    return errorKey((err && err.message) || String(err));
  }

  function errorText(err) { return t(keyOfError(err)); }

  function showError(err) {
    const message = (err && err.message) || String(err);
    W.notice = { kind: 'error', key: keyOfError(err), detail: detailOf(message) };
  }

  // Errors of actions started outside the wizard (Settings) go to a toast, the wizard shows its box.
  function report(err) {
    if (W.root && !W.root.hidden) { showError(err); render(); }
    else W.deps.toast(errorText(err));
  }

  function formatBytes(bytes) {
    const gb = bytes / 1073741824;
    if (gb >= 1) return gb.toLocaleString(locale(), { maximumFractionDigits: 1 }) + ' GB';
    return (bytes / 1048576).toLocaleString(locale(), { maximumFractionDigits: 1 }) + ' MB';
  }

  function hasBridge() { return !!(window.pywebview && window.pywebview.api); }

  function pickFolder() {
    if (hasBridge()) return window.pywebview.api.pick_folder();
    return Promise.resolve(window.prompt(t('wz_loc_type_path')) || null);
  }

  function openLogs() {
    if (W.probe && hasBridge()) window.pywebview.api.open_folder(W.probe.logs_dir);
  }

  function loadProbe() {
    return api('GET', '/api/wizard/probe').then(function (data) { W.probe = data; return data; });
  }

  // ---- installation progress -------------------------------------------------------
  function stopPolling() {
    if (W.timer) { clearTimeout(W.timer); W.timer = null; }
  }

  function finishedAll(events) {
    return (events || []).some(function (e) {
      return e.stage === 'mark' && (e.state === 'done' || e.state === 'skipped');
    });
  }

  function updateSpeed() {
    const events = (W.progress && W.progress.events) || [];
    const last = events[events.length - 1];
    const s = W.speed;
    if (!last || last.state !== 'progress' || !last.total) { s.rate = 0; return; }
    const now = Date.now();
    if (s.stage === last.stage && last.done >= s.bytes && now > s.time) {
      const rate = (last.done - s.bytes) * 1000 / (now - s.time);
      s.rate = s.rate ? s.rate * 0.7 + rate * 0.3 : rate;
    } else {
      s.rate = 0;
    }
    s.stage = last.stage; s.bytes = last.done; s.time = now;
  }

  function visible() { return !!(W.root && !W.root.hidden); }

  // Polls while an installation runs and the wizard is shown; show() resumes it.
  function poll() {
    stopPolling();
    api('GET', '/api/wizard/progress').then(function (data) {
      W.progress = data;
      updateSpeed();
      if (data.running) {
        if (visible()) W.timer = setTimeout(poll, POLL_MS);
        return null;
      }
      if (!data.error && finishedAll(data.events)) {
        return loadProbe().then(function () { W.step = 'selftest'; });
      }
      return null;
    }).catch(function (err) {
      showError(err);
      if (visible()) W.timer = setTimeout(poll, POLL_MS * 3);
    }).then(render);
  }

  function startInstall() {
    W.notice = null;
    const before = W.progress;
    W.progress = { events: [], running: true, error: null };
    W.step = 'install';
    render();
    api('POST', '/api/wizard/install').then(poll).catch(function (err) {
      // refused (busy, queue_running, unsupported): nothing started, so show the earlier stages
      // again with Continue / Try again instead of a screen that only offers Pause
      W.progress = { events: (before && before.events) || [], running: false,
                     error: (before && before.error) || null };
      showError(err);
      render();
    });
  }

  function pauseInstall() {
    api('POST', '/api/wizard/cancel').catch(function () { return null; }).then(poll);
  }

  // ---- screens -----------------------------------------------------------------------
  function go(next) { W.notice = null; W.step = next; render(); }

  function button(label, onclick, opts) {
    const o = opts || {};
    return h('button', { type: 'button', 'class': o.primary ? 'primary' : null,
                         disabled: o.disabled || !!W.busy, onclick: onclick, text: label });
  }

  function buttons() {
    return h.apply(null, ['div', { 'class': 'row wz-buttons' }].concat(Array.prototype.slice.call(arguments)));
  }

  function header() {
    const index = STEPS.indexOf(W.step);
    return h('div', { 'class': 'wz-header' },
      h('h2', { text: t('wz_title') }),
      h('span', { 'class': 'wz-steps', text: t('wz_step', { n: index + 1, total: STEPS.length }) + ' · ' +
                                             t('wz_step_' + W.step) }));
  }

  function noticeBox() {
    if (!W.notice) return null;
    return h('div', { 'class': 'wz-notice wz-' + W.notice.kind, role: W.notice.kind === 'error' ? 'alert' : 'status' },
      h('div', { text: t(W.notice.key, W.notice.vars) }),
      W.notice.detail ? h('div', { 'class': 'wz-detail', text: W.notice.detail }) : null);
  }

  // The probe could not read the installation record or check the model: say so, with the reason.
  function probeErrorBox() {
    const error = W.probe && W.probe.probe_error;
    if (!error) return null;
    return h('div', { 'class': 'wz-notice wz-error', role: 'alert' },
      h('div', { text: t(errorKey(error)) }), h('div', { 'class': 'wz-detail', text: detailOf(error) }));
  }

  function screenWelcome() {
    return [h('h3', { text: t('wz_welcome_heading') }),
      h('p', { text: t('wz_welcome_intro') }),
      h('p', { text: t('wz_welcome_download') }),
      h('p', { text: t('wz_welcome_once') }),
      h('p', { 'class': 'wz-muted', text: t('wz_welcome_privacy') }),
      buttons(button(t('wz_btn_next'), function () { go('hardware'); }, { primary: true }))];
  }

  function screenHardware() {
    const p = W.probe;
    const tier = p.tier;
    const gpuLines = p.gpus.length ? p.gpus.map(function (g) {
      return h('div', { text: t('wz_hw_gpu_line', { name: g.name, driver: g.driver,
        vram: (g.vram_total_mib / 1024).toLocaleString(locale(), { maximumFractionDigits: 0 }) }) });
    }) : [h('div', { text: t('wz_hw_no_gpu') })];
    const driver = p.gpus.length ? p.gpus[0].driver : '';
    const reason = tier.reason && tier.reason !== 'ok' ? t('wz_reason_' + tier.reason, { driver: driver }) : '';
    const unsupported = tier.name === 'unsupported';
    return [h('h3', { text: t('wz_hw_heading') }),
      h('dl', { 'class': 'wz-facts' },
        h('dt', { text: t('wz_hw_gpu') }), h.apply(null, ['dd', {}].concat(gpuLines)),
        h('dt', { text: t('wz_hw_ram') }), h('dd', { text: formatBytes(p.ram_mib * 1048576) }),
        h('dt', { text: t('wz_hw_tier') }),
        h('dd', {}, h('strong', { text: t('wz_tier_' + tier.name) }), h('div', { text: t('wz_tier_desc_' + tier.name) })),
        h('dt', { text: t('wz_hw_speed') }), h('dd', { text: t('wz_speed_' + tier.name) })),
      reason ? h('p', { 'class': 'wz-warning', text: reason }) : null,
      tier.name === 'cpu' && tier.reason === 'driver_too_old' ? h('p', { text: t('wz_hw_cpu_meanwhile') }) : null,
      unsupported ? h('p', { 'class': 'wz-warning',
                             text: p.cpu_tier_enabled ? t('wz_hw_unsupported_help') : t('wz_hw_gpu_only') }) : null,
      buttons(button(t('wz_btn_back'), function () { go('welcome'); }),
              button(t('wz_btn_next'), function () { go('location'); }, { primary: true, disabled: unsupported }))];
  }

  function chooseFolder() {
    pickFolder().then(function (folder) {
      if (!folder) return null;
      W.busy = t('wz_loc_moving'); W.notice = null; render();
      return api('POST', '/api/wizard/location', { path: folder }).then(function (data) {
        // a drive root or a folder with other files becomes <folder>\OwlOCR: show the real one
        W.notice = { kind: 'info', key: 'wz_loc_now', vars: { folder: data.data_root }, detail: '' };
        return loadProbe();
      });
    }).catch(showError).then(function () { W.busy = ''; render(); });
  }

  function haveEngine() {
    const copy = W.copy;
    pickFolder().then(function (folder) {
      if (!folder) return null;
      W.busy = t('wz_loc_checking'); W.notice = null; render();
      return api('POST', '/api/wizard/adopt', { path: folder, copy: copy }).then(function () {
        W.notice = { kind: 'info', key: 'wz_loc_adopted', detail: '' };
        return loadProbe();
      });
    }).catch(showError).then(function () { W.busy = ''; render(); });
  }

  function copyBox() {
    const box = h('input', { type: 'checkbox', id: 'wzCopy', checked: W.copy });
    box.addEventListener('change', function () { W.copy = box.checked; });
    return box;
  }

  function screenLocation() {
    const p = W.probe;
    const need = p.install ? 0 : Math.max(0, p.required_bytes - (p.model_ready ? MODEL_BYTES : 0));
    return [h('h3', { text: t('wz_loc_heading') }),
      h('dl', { 'class': 'wz-facts' },
        h('dt', { text: t('wz_loc_folder') }), h('dd', { 'class': 'wz-path', text: p.data_root }),
        h('dt', { text: t('wz_loc_free', { free: formatBytes(p.free_bytes) }) }),
        h('dd', { text: t('wz_loc_need', { need: formatBytes(need) }) })),
      p.free_bytes < need ? h('p', { 'class': 'wz-warning', text: t('wz_loc_low') }) : null,
      p.env_override ? h('p', { 'class': 'wz-muted', text: t('wz_loc_env') }) : null,
      h('p', { 'class': 'wz-muted', text: t('wz_loc_have_help') }),
      h('label', { 'class': 'wz-check' }, copyBox(), ' ' + t('wz_loc_copy')),
      W.busy ? h('p', { 'class': 'wz-busy', text: W.busy }) : null,
      buttons(button(t('wz_btn_back'), function () { go('hardware'); }),
              p.env_override ? null : button(t('wz_btn_choose_folder'), chooseFolder),
              button(t('wz_btn_have_engine'), haveEngine),
              button(t('wz_btn_install'), startInstall, { primary: true }))];
  }

  function stageList() {
    const latest = {};
    ((W.progress && W.progress.events) || []).forEach(function (e) { latest[e.stage] = e; });
    return h.apply(null, ['ol', { 'class': 'wz-stages' }].concat(STAGES.map(function (stage) {
      const e = latest[stage];
      const state = !e ? 'pending' : (e.state === 'failed' && e.message === 'cancelled' ? 'paused' : e.state);
      let detail = null;
      if (e && (state === 'progress' || state === 'start')) {
        const parts = [];
        if (e.total > 0) {
          const bytes = e.total > 100000;
          parts.push(t('wz_inst_of', { done: bytes ? formatBytes(e.done) : e.done,
                                       total: bytes ? formatBytes(e.total) : e.total }));
          if (bytes && W.speed.stage === stage && W.speed.rate > 0) {
            parts.push(t('wz_inst_speed', { rate: formatBytes(W.speed.rate) }));
          }
        }
        if (e.message && e.message !== 'checking') parts.push(e.message);
        detail = h('div', { 'class': 'wz-stage-detail' },
          e.total > 0 ? h('progress', { max: String(e.total), value: String(Math.min(e.done, e.total)) }) : null,
          h('span', { text: parts.join(' · ') }));
      }
      return h('li', { 'class': 'wz-stage wz-' + state },
        h('span', { 'class': 'wz-stage-name', text: t('wz_stage_' + stage) }),
        h('span', { 'class': 'wz-stage-state', text: t('wz_state_' + state) }), detail);
    })));
  }

  function screenInstall() {
    const running = !!(W.progress && W.progress.running);
    const error = W.progress && W.progress.error;
    const paused = !!error && errorKey(error) === 'wz_error_cancelled';
    const nothingYet = !(W.progress && W.progress.events && W.progress.events.length);
    const lines = [h('h3', { text: t('wz_inst_heading') }), h('p', { 'class': 'wz-muted', text: t('wz_inst_intro') })];
    if (!running && !error && W.probe && W.probe.interrupted && nothingYet) lines.push(h('p', { text: t('wz_inst_interrupted') }));
    if (paused) {
      lines.push(h('p', { text: t('wz_inst_paused') }));
    } else if (error) {
      lines.push(h('div', { 'class': 'wz-notice wz-error', role: 'alert' },
        h('div', { text: t('wz_inst_failed') + ' ' + t(errorKey(error)) }),
        h('div', { 'class': 'wz-detail', text: detailOf(error) })));
    }
    lines.push(stageList());
    lines.push(buttons(
      running ? button(t('wz_btn_pause'), pauseInstall) : null,
      running ? null : button(error && !paused ? t('wz_btn_retry') : t('wz_btn_continue'), startInstall, { primary: true }),
      button(t('wz_btn_open_logs'), openLogs)));
    return lines;
  }

  function screenSelftest() {
    const record = W.probe && W.probe.install;
    const seconds = record ? record.selftest_seconds : null;
    const tierName = record ? record.tier : W.probe.tier.name;
    return [h('h3', { text: t('wz_st_heading') }),
      h('p', { text: seconds !== null && seconds !== undefined ?
        t('wz_st_result', { seconds: Number(seconds).toLocaleString(locale(), { maximumFractionDigits: 1 }) }) :
        t('wz_st_unknown') }),
      h('p', { text: t('wz_st_estimate', { speed: t('wz_speed_' + tierName) }) }),
      buttons(button(t('wz_btn_next'), function () { go('dicts'); }, { primary: true }))];
  }

  // ---- dictionaries (optional step and Settings) ---------------------------------------
  function loadDicts() {
    return api('GET', '/api/dictionaries').then(function (data) { W.dicts = data.languages; return W.dicts; });
  }

  function anyDictRunning() {
    return (W.dicts || []).some(function (d) { return d.running; });
  }

  function pollDicts() {
    if (W.dictTimer) { clearTimeout(W.dictTimer); W.dictTimer = null; }
    loadDicts().then(function () {
      if (anyDictRunning()) W.dictTimer = setTimeout(pollDicts, POLL_MS);
    }).catch(report).then(redrawDicts);
  }

  function dictLabel(d) {
    return t('wz_dict_item', { language: t('wz_dict_lang_' + d.language), size: formatBytes(d.size),
                               licence: d.licence });
  }

  function dictState(d) {
    if (d.running) {
      return t('wz_dict_downloading', { done: formatBytes(d.done), total: formatBytes(d.total || d.size) });
    }
    if (d.installed) return t('wz_dict_installed');
    return t('wz_dict_missing');
  }

  function dictError(d) {
    return d.error ? h('div', { 'class': 'wz-notice wz-error', role: 'alert' },
      h('div', { text: t(errorKey(d.error)) }), h('div', { 'class': 'wz-detail', text: detailOf(d.error) })) : null;
  }

  function installDicts(languages) {
    if (W.dictStarting) return Promise.resolve(null);   // a second click while the POSTs run
    W.dictStarting = true;
    redrawDicts();
    return Promise.all(languages.map(function (language) {
      return api('POST', '/api/dictionaries/' + language);
    })).catch(report).then(function () {
      W.dictStarting = false;
      return pollDicts();
    });
  }

  function redrawDicts() {
    if (W.step === 'dicts' && visible()) render();
    renderDictPanel();
  }

  function screenDicts() {
    if (W.dicts === null) { pollDicts(); return [h('h3', { text: t('wz_dict_heading') })]; }
    const rows = W.dicts.map(function (d) {
      const box = h('input', { type: 'checkbox', checked: d.installed || W.dictChoice[d.language],
                               disabled: d.installed || d.running });
      box.addEventListener('change', function () { W.dictChoice[d.language] = box.checked; render(); });
      return h('li', { 'class': 'wz-dict' },
        h('label', {}, box, ' ' + dictLabel(d)),
        h('span', { 'class': 'wz-stage-state', text: dictState(d) }),
        d.running ? h('progress', { max: String(d.total || d.size), value: String(d.done) }) : null,
        dictError(d));
    });
    const wanted = W.dicts.filter(function (d) { return !d.installed && W.dictChoice[d.language]; })
      .map(function (d) { return d.language; });
    const running = anyDictRunning() || W.dictStarting;
    return [h('h3', { text: t('wz_dict_heading') }),
      h('p', { text: t('wz_dict_intro') }),
      h('p', { 'class': 'wz-muted', text: t('wz_dict_source') }),
      h.apply(null, ['ul', { 'class': 'wz-dicts' }].concat(rows)),
      buttons(button(t('wz_btn_skip'), function () { go('done'); }, { disabled: running }),
              wanted.length ? button(t('wz_btn_download'), function () { installDicts(wanted); },
                                     { primary: true, disabled: running })
                            : button(t('wz_btn_next'), function () { go('done'); },
                                     { primary: true, disabled: running }))];
  }

  function renderDictPanel() {
    const panel = W.dictPanel;
    if (!panel || !W.dicts) return;
    panel.textContent = '';
    const rows = W.dicts.map(function (d) {
      const action = d.installed
        ? h('button', { type: 'button', disabled: d.running || W.dictStarting, text: t('wz_btn_remove_dict'), onclick: function () {
            W.deps.confirmDialog(t('wz_dict_remove_confirm', { language: t('wz_dict_lang_' + d.language) }))
              .then(function (yes) {
                if (!yes) return null;
                return api('DELETE', '/api/dictionaries/' + d.language).then(pollDicts);
              }).catch(function (err) { W.deps.toast(errorText(err)); });
          } })
        : h('button', { type: 'button', disabled: d.running || W.dictStarting, text: t('wz_btn_install_dict'),
                        onclick: function () { installDicts([d.language]); } });
      return h('li', { 'class': 'wz-dict' },
        h('span', { text: dictLabel(d) }),
        h('span', { 'class': 'wz-stage-state', text: dictState(d) }),
        action, dictError(d));
    });
    panel.appendChild(h('h2', { text: t('wz_dict_settings_heading') }));
    panel.appendChild(h('p', { 'class': 'wz-muted', text: t('wz_dict_intro') + ' ' + t('wz_dict_settings_source') }));
    panel.appendChild(h.apply(null, ['ul', { 'class': 'wz-dicts' }].concat(rows)));
  }

  function renderDictionaries(container) {
    W.dictPanel = container;
    pollDicts();
  }

  function screenDone() {
    return [h('h3', { text: t('wz_done_heading') }),
      h('p', { text: t('wz_done_body') }),
      h('p', { 'class': 'wz-muted', text: t('wz_done_note') }),
      buttons(button(t('wz_btn_start_using'), finish, { primary: true }))];
  }

  function finish() {
    stopPolling();
    W.deps.showView('queue');
  }

  const SCREENS = { welcome: screenWelcome, hardware: screenHardware, location: screenLocation,
                    install: screenInstall, selftest: screenSelftest, dicts: screenDicts,
                    done: screenDone };

  function render() {
    if (!W.root) return;
    W.root.textContent = '';
    const body = W.probe || W.step === 'welcome' ? SCREENS[W.step]() : [];
    W.root.appendChild(h.apply(null, ['div', { 'class': 'wz' }, header(), probeErrorBox(), noticeBox()].concat(body)));
  }

  // ---- public API ------------------------------------------------------------------
  function init(deps) {
    W.deps = deps;
    W.root = document.getElementById('viewWizard');
    new MutationObserver(function () {
      if (!W.root.hidden) render();
      renderDictPanel();
    })
      .observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
  }

  function show() {
    W.notice = W.nextNotice;         // a message left by a Settings action (Move) survives the switch
    W.nextNotice = null;
    return Promise.all([loadProbe(), api('GET', '/api/wizard/progress')]).then(function (both) {
      W.progress = both[1];
      if (W.probe.installed) W.step = 'done';
      else if (W.progress.running || W.probe.interrupted) W.step = 'install';
      else if (['selftest', 'dicts', 'done'].indexOf(W.step) >= 0) W.step = 'welcome';
      render();
      if (W.progress.running) poll();
    }).catch(function (err) { showError(err); render(); });
  }

  // ---- Settings: engine actions ------------------------------------------------------
  // Verify, Reinstall and Move answer only when their file work is done (verify reads 6.7 GB,
  // move may copy it): while one runs, all four engine buttons are disabled and the pressed one
  // says what is happening. The server refuses a second action anyway (409 busy).
  function setEngineButtons(disabled) {
    ENGINE_BUTTONS.forEach(function (id) {
      const b = document.getElementById(id);
      if (b) b.disabled = disabled;
    });
  }

  function engineBusy(buttonId, busyKey, work) {
    if (W.engineBusy) return Promise.resolve(null);
    const pressed = document.getElementById(buttonId);
    W.engineBusy = true;
    setEngineButtons(true);
    if (pressed) { pressed.textContent = t(busyKey); pressed.setAttribute('aria-busy', 'true'); }
    return Promise.resolve().then(work).catch(report).then(function (result) {
      W.engineBusy = false;
      setEngineButtons(false);
      if (pressed) {            // its own label again, in the language shown now
        pressed.textContent = pressed.dataset.i18n ? t(pressed.dataset.i18n) : '';
        pressed.removeAttribute('aria-busy');
      }
      return result;
    });
  }

  function verify() {
    return engineBusy('btnVerify', 'wz_eng_verifying', function () {
      return api('POST', '/api/engine/verify').then(function (result) {
        const count = Object.keys((result && result.problems) || {}).length;
        W.deps.toast(count ? t('t_verify_problems', { n: count }) : t('t_verify_ok'));
        return result;
      });
    });
  }

  function reinstall() {
    return W.deps.confirmDialog(t('wz_eng_reinstall_confirm')).then(function (yes) {
      if (!yes) return null;
      return engineBusy('btnReinstall', 'wz_eng_working', function () {
        return api('POST', '/api/engine/reinstall').then(function () {
          W.step = 'location';
          W.deps.showView('wizard');
        });
      });
    });
  }

  function remove() {
    return W.deps.confirmDialog(t('confirm_remove_engine')).then(function (yes) {
      if (!yes) return null;
      return engineBusy('btnRemoveEngine', 'wz_eng_working', function () {
        return api('POST', '/api/engine/remove').then(function () { W.deps.showView('wizard'); });
      });
    });
  }

  function move() {
    if (W.engineBusy) return Promise.resolve(null);
    return pickFolder().then(function (folder) {
      if (!folder) return null;
      return W.deps.confirmDialog(t('wz_eng_move_confirm', { folder: folder })).then(function (yes) {
        if (!yes) return null;
        return engineBusy('btnMove', 'wz_loc_moving', function () {
          return api('POST', '/api/engine/move', { path: folder }).then(function (data) {
            // the server may have added \OwlOCR to the chosen folder: name the real one
            const leftovers = (data && data.leftovers) || [];
            W.nextNotice = { kind: 'info', key: 'wz_loc_now', vars: { folder: data.data_root },
                             detail: leftovers.length ? t('wz_eng_leftovers') + ' ' + leftovers.join('; ') : '' };
            W.deps.toast(t('wz_eng_moved'));
            W.step = 'install';
            W.deps.showView('wizard');
          });
        });
      });
    }).catch(report);
  }

  window.OwlWizard = { init: init, show: show, render: render, reinstall: reinstall, move: move,
                       renderDictionaries: renderDictionaries, verify: verify, remove: remove,
                       errorText: errorText };
})();
