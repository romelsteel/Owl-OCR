'use strict';
// Review screen (design 10.4): the page image with block boxes (0..999 coordinates), the text
// beside it, suspicious words underlined, repaired words showing the original on hover, blocks
// editable and saved through POST /api/jobs/<id>/document. Text is always inserted with
// textContent, never parsed as markup: OCR output may contain HTML (tables) or anything else.
window.OwlReview = (function () {
  const $ = function (id) { return document.getElementById(id); };
  const SVG_NS = 'http://www.w3.org/2000/svg';
  let deps = null;      // {api, toast, showView, getFormats, isRunning}
  let jobId = null;
  let jobName = '';
  let doc = null;
  let pageIdx = 0;
  let readOnly = false;
  let seq = 0;           // bumped by every open(): a late answer for an older job is dropped
  // Block saves run one after another on this chain; it resolves to false when the latest one
  // failed. "Save again" waits for it, because the press on the button is what blurs (and so
  // saves) the block being edited. Only a failure of a save that this press started, or that was
  // still running, stops the export: an old failure was already reported and must not keep
  // the button dead.
  let saving = Promise.resolve(true);
  let saveCount = 0;     // saves ever queued
  let inFlight = 0;      // saves queued and not finished yet
  let pressMark = null;  // saveCount when the "Save again" button was pressed

  function t(key, vars) { return window.OwlI18n.t(key, vars); }

  function init(dependencies) {
    deps = dependencies;
    $('revBack').addEventListener('click', function () { deps.showView('queue'); });
    $('revPrev').addEventListener('click', function () { go(pageIdx - 1); });
    $('revNext').addEventListener('click', function () { go(pageIdx + 1); });
    // mousedown comes before the blur it causes, so a save queued after this mark is this press's
    $('revExport').addEventListener('mousedown', function () { pressMark = saveCount; });
    $('revExport').addEventListener('click', exportAgain);
  }

  async function open(id, name) {
    const my = ++seq;
    jobId = id;
    jobName = name || '';
    doc = null;
    pageIdx = 0;
    readOnly = deps.isRunning(id);
    saving = Promise.resolve(true);   // a save on the previous job never gates this job's export
    deps.showView('review');
    $('revName').textContent = jobName;
    $('revText').textContent = '';
    $('revBoxes').textContent = '';
    $('revImg').removeAttribute('src');
    let loaded;
    try {
      loaded = await deps.api('GET', '/api/jobs/' + encodeURIComponent(id) + '/document');
    } catch (err) {
      if (my !== seq) return;
      $('revInfo').textContent = t('rev_no_document');
      updateNav();
      return;
    }
    if (my !== seq) return;
    doc = loaded;
    render();
  }

  function go(index) {
    if (!doc || index < 0 || index >= doc.pages.length) return;
    pageIdx = index;
    render();
  }

  function updateNav() {
    const total = doc ? doc.pages.length : 0;
    $('revPageLabel').textContent = total ? t('rev_page', { n: pageIdx + 1, total: total }) : '';
    $('revPrev').disabled = !doc || pageIdx <= 0;
    $('revNext').disabled = !doc || pageIdx >= total - 1;
    $('revExport').disabled = !doc || readOnly;
  }

  function render() {
    updateNav();
    $('revName').textContent = jobName;
    if (!doc) return;
    $('revInfo').textContent = readOnly ? t('rev_readonly') : t('rev_hint');
    const page = doc.pages[pageIdx];
    const boxes = $('revBoxes');
    const text = $('revText');
    boxes.textContent = '';
    text.textContent = '';
    if (!page) return;
    $('revImg').src = '/api/jobs/' + encodeURIComponent(jobId) + '/page/' + page.index + '.png';
    if (!page.blocks.length) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = t('rev_empty_page');
      text.appendChild(empty);
      return;
    }
    page.blocks.forEach(function (block, bi) {
      if (block.box) {
        const r = document.createElementNS(SVG_NS, 'rect');
        r.setAttribute('x', block.box[0]);
        r.setAttribute('y', block.box[1]);
        r.setAttribute('width', Math.max(1, block.box[2] - block.box[0]));
        r.setAttribute('height', Math.max(1, block.box[3] - block.box[1]));
        r.dataset.b = String(bi);
        r.addEventListener('click', function () { setActive(bi, true); });
        boxes.appendChild(r);
      }
      text.appendChild(blockElement(page, block, bi));
    });
  }

  function blockElement(page, block, bi) {
    const wrap = document.createElement('div');
    wrap.className = 'rev-block';
    wrap.dataset.b = String(bi);
    const label = document.createElement('div');
    label.className = 'rev-label';
    const key = 'label_' + block.label;
    const translated = t(key);
    label.textContent = translated === key ? block.label : translated;
    const body = document.createElement('div');
    body.className = 'rev-body';
    if (!readOnly) body.setAttribute('contenteditable', 'plaintext-only');
    fillText(body, block);
    body.addEventListener('focus', function () { setActive(bi, false); });
    body.addEventListener('blur', function () {
      // Everything the save needs is taken now: by the time a queued save runs, another job
      // (possibly a running, read-only one) may be open.
      const edit = { id: jobId, readOnly: readOnly, text: body.innerText.replace(/\n$/, '') };
      saveCount += 1;
      inFlight += 1;
      saving = saving
        .then(function () { return save(edit, page, bi, body); })
        .catch(function () { return false; })
        .then(function (ok) { inFlight -= 1; return ok; });
    });
    wrap.addEventListener('click', function () { setActive(bi, false); });
    wrap.append(label, body);
    return wrap;
  }

  function fillText(node, block) {
    node.textContent = '';
    const text = block.text || '';
    const flags = (block.flags || [])
      .filter(function (f) { return f.start >= 0 && f.end <= text.length && f.end > f.start; })
      .sort(function (a, b) { return a.start - b.start; });
    let pos = 0;
    flags.forEach(function (f) {
      if (f.start < pos) return;
      if (f.start > pos) node.appendChild(document.createTextNode(text.slice(pos, f.start)));
      const span = document.createElement('span');
      if (f.kind === 'repaired') {
        span.className = 'flag-repaired';
        span.title = t('rev_repaired', { original: f.original || '' });
      } else {
        span.className = 'flag-suspicious';
        span.title = f.note || t('rev_suspicious');
      }
      span.textContent = text.slice(f.start, f.end);
      node.appendChild(span);
      pos = f.end;
    });
    if (pos < text.length) node.appendChild(document.createTextNode(text.slice(pos)));
  }

  function setActive(bi, scrollText) {
    document.querySelectorAll('#revBoxes rect').forEach(function (r) {
      r.classList.toggle('active', r.dataset.b === String(bi));
    });
    document.querySelectorAll('#revText .rev-block').forEach(function (b) {
      const on = b.dataset.b === String(bi);
      b.classList.toggle('active', on);
      if (on && scrollText) b.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    });
  }

  // Resolves to true when the block is saved (or unchanged), false when saving failed.
  async function save(edit, page, bi, body) {
    if (edit.readOnly) return true;
    const block = page.blocks[bi];
    if (edit.text === block.text) return true;
    try {
      const saved = await deps.api('POST', '/api/jobs/' + encodeURIComponent(edit.id) + '/document',
        { page: page.index, block: bi, text: edit.text });
      page.blocks[bi] = saved;
      fillText(body, saved);
      deps.toast(t('rev_saved'));
      return true;
    } catch (err) {
      deps.toast(t('t_error', { e: err.message }));
      fillText(body, block);
      return false;
    }
  }

  async function exportAgain() {
    const id = jobId;
    if (!id) return;
    // Did this press start a save (it blurred the block being edited), or is one still running?
    const waitedOn = (pressMark !== null && saveCount > pressMark) || inFlight > 0;
    pressMark = null;
    const saved = await saving;   // the edit the user just made must be in the export
    // That save's own error toast has just told the user why nothing is exported. An older
    // failure was reported when it happened and does not block the export.
    if (!saved && waitedOn) return;
    try {
      const result = await deps.api('POST', '/api/jobs/' + encodeURIComponent(id) + '/export',
        { formats: deps.getFormats() });
      const names = Object.values(result.outputs).map(function (p) { return p.split(/[\\/]/).pop(); });
      deps.toast(t('t_exported', { files: names.join(', ') }));
    } catch (err) {
      deps.toast(t('t_error', { e: err.message }));
    }
  }

  function refreshLanguage() { if (doc) render(); else updateNav(); }

  return { init: init, open: open, refreshLanguage: refreshLanguage };
})();
