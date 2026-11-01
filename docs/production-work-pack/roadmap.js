/* Local planning only. No requests, command execution, or automatic verification. */
(() => {
  'use strict';
  const data = window.ROADMAP_DATA;
  const $ = id => document.getElementById(id);
  if (!data || !Array.isArray(data.tasks)) {
    $('stage-title').textContent = 'Roadmap data is unavailable';
    $('stage-notice').textContent = 'Keep roadmap-data.js beside this page, then reload.';
    return;
  }
  const owners = ['Sol', 'Freebuff', 'You'];
  const tasks = data.tasks;
  const byId = new Map(tasks.map(task => [task.id, task]));
  const storageKey = `boom-production-roadmap:${data.version}`;
  const labels = { ready: 'Ready to start', todo: 'To do', doing: 'In progress', done: 'Manually complete', blocked: 'Blocked', recheck: 'Needs recheck' };
  let records = {}, selected = null, noticeTimer, drawFrame;
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const list = value => Array.isArray(value) ? value : [];
  const record = id => records[id] || { status: 'todo', notes: '', evidence: '' };
  const dependencies = task => list(task.deps);
  const depsDone = task => dependencies(task).every(id => byId.has(id) && record(id).status === 'done');
  const status = task => record(task.id).status === 'done' ? 'done' : !depsDone(task) ? 'blocked' : record(task.id).needsRecheck ? 'recheck' : record(task.id).status === 'doing' ? 'doing' : 'ready';
  function announce(message) {
    clearTimeout(noticeTimer);
    $('announcement').textContent = message;
    noticeTimer = setTimeout(() => { $('announcement').textContent = ''; }, 10000);
  }
  function parseState(raw) {
    if (raw.length > 2000000) throw new Error('This progress file is too large (maximum 2 MB).');
    const parsed = JSON.parse(raw);
    if (!parsed || parsed.version !== data.version || !parsed.records || typeof parsed.records !== 'object' || Array.isArray(parsed.records)) throw new Error('Use a progress file exported from this roadmap version.');
    const safe = Object.create(null);
    for (const [id, item] of Object.entries(parsed.records)) {
      if (!byId.has(id)) continue;
      if (!item || typeof item !== 'object' || !['todo', 'doing', 'done'].includes(item.status)) throw new Error(`Invalid status for ${id}.`);
      for (const field of ['notes', 'evidence']) if (item[field] !== undefined && (typeof item[field] !== 'string' || item[field].length > 20000)) throw new Error(`Invalid ${field} for ${id}.`);
      safe[id] = { status: item.status, notes: item.notes || '', evidence: item.evidence || '', needsRecheck: item.needsRecheck === true };
      if (safe[id].status === 'done' && !safe[id].evidence.trim()) { safe[id].status = 'todo'; safe[id].needsRecheck = true; }
    }
    return safe;
  }
  function invalidate() {
    const reset = [];
    let changed = true;
    while (changed) {
      changed = false;
      for (const task of tasks) {
        const item = record(task.id);
        if ((item.status === 'done' || item.status === 'doing') && !depsDone(task)) {
          records[task.id] = { ...item, status: 'todo', needsRecheck: true };
          reset.push(task.id);
          changed = true;
        }
      }
    }
    return reset;
  }
  function persist() {
    try { localStorage.setItem(storageKey, JSON.stringify({ version: data.version, records })); return true; }
    catch { announce('Browser storage is unavailable. Export progress before closing this page.'); return false; }
  }
  try {
    const saved = localStorage.getItem(storageKey);
    if (saved) { records = parseState(saved); const reset = invalidate(); if (reset.length) announce(`Prerequisites changed. ${reset.join(', ')} now need recheck.`); }
  } catch { announce('Saved progress could not be loaded. This page starts with a fresh local record.'); }
  $('stage-title').textContent = data.stage || 'Evidence review';
  $('stage-notice').textContent = data.notice || 'A planning snapshot, not live execution status.';
  $('snapshot-date').textContent = `Snapshot checked: ${data.checkedAt || 'not recorded'} · Roadmap v${data.version}`;
  for (const [id, key] of [['guide-link', 'guide'], ['taxonomy-link', 'taxonomy']]) {
    const path = data.links?.[key];
    if (typeof path === 'string' && !/^(?:[a-z]+:|\/\/)/i.test(path)) $(id).setAttribute('href', path);
  }
  list(data.milestones).forEach((item, index) => {
    const card = el('article', 'milestone');
    card.append(el('div', 'milestone-label', `${String(index + 1).padStart(2, '0')} / ${item.state || 'Snapshot'}`), el('h3', '', item.title), el('p', '', item.detail));
    if (item.evidence) card.append(el('p', 'milestone-evidence', `Evidence: ${Array.isArray(item.evidence) ? item.evidence.join(' · ') : item.evidence}`));
    $('milestones').append(card);
  });
  const taskOrder = [...tasks].sort((a, b) => Number(a.phase) - Number(b.phase) || a.priority.localeCompare(b.priority) || tasks.indexOf(a) - tasks.indexOf(b));
  function renderStarts() {
    $('start-grid').replaceChildren();
    for (const owner of owners) {
      const candidates = taskOrder.filter(task => task.owner === owner && ['ready', 'recheck', 'doing'].includes(status(task)));
      const task = candidates.find(item => !item.optional) || candidates[0];
      const card = el(task ? 'button' : 'div', `start-card${task ? '' : ' unavailable'}`);
      card.append(el('span', 'start-owner', owner), el('strong', '', task ? task.title : 'No task ready yet'));
      card.append(el('small', '', task ? `${task.id} · ${task.priority} · ${labels[status(task)]}${task.optional ? ' · Optional' : ''}` : tasks.filter(item => item.owner === owner).every(item => status(item) === 'done') ? 'All tasks for this owner are manually complete.' : 'Complete prerequisite work to unlock the next task.'));
      if (task) { card.type = 'button'; card.addEventListener('click', () => openTask(task.id)); }
      $('start-grid').append(card);
    }
  }
  function makeCard(task) {
    const state = status(task), card = el('button', `task-card ${state}`);
    card.type = 'button'; card.dataset.taskId = task.id;
    card.setAttribute('aria-label', `${task.id}: ${task.title}. Owner ${task.owner}. ${task.priority}. ${labels[state]}. Open task details.`);
    const meta = el('span', 'task-meta');
    meta.append(el('span', 'task-id', task.id), el('span', `priority ${task.priority.toLowerCase()}`, task.priority), el('span', 'task-owner', task.owner));
    const bottom = el('span', 'task-bottom'), deps = dependencies(task);
    bottom.append(el('span', 'status-label', labels[state]), el('span', '', `${task.optional ? 'Optional · ' : ''}${deps.length ? `${deps.filter(id => record(id).status === 'done').length}/${deps.length} prerequisites` : 'No prerequisites'}`));
    card.append(meta, el('span', 'task-name', task.title), bottom);
    card.addEventListener('click', () => openTask(task.id));
    return card;
  }
  function renderMap() {
    const owner = $('owner-filter').value, filter = $('status-filter').value, optional = $('optional-filter').checked;
    const shownOwners = owner === 'all' ? owners : [owner];
    const visible = tasks.filter(task => shownOwners.includes(task.owner) && (optional || !task.optional) && (filter === 'all' || status(task) === filter));
    $('work-map').style.setProperty('--lanes', shownOwners.length);
    $('lane-headings').replaceChildren(); $('phase-rows').replaceChildren();
    for (const name of shownOwners) {
      const heading = el('div', 'lane-heading');
      heading.append(el('span', 'owner-icon', name === 'Freebuff' ? 'Fb' : name.slice(0, 1)), el('span', '', name), el('small', '', `${visible.filter(task => task.owner === name).length} tasks`));
      $('lane-headings').append(heading);
    }
    for (const phase of list(data.phases)) {
      const phaseTasks = visible.filter(task => String(task.phase) === String(phase.id));
      if (!phaseTasks.length) continue;
      const row = el('section', 'phase-row'), heading = el('h3', 'phase-title');
      heading.append(el('span', '', `Phase ${phase.id}`), document.createTextNode(phase.title));
      const grid = el('div', 'phase-grid');
      for (const name of shownOwners) {
        const cell = el('div', 'lane-cell'), owned = phaseTasks.filter(task => task.owner === name);
        if (owned.length) cell.append(el('p', 'mobile-owner', name));
        owned.forEach(task => cell.append(makeCard(task)));
        if (!owned.length) cell.classList.add('empty-lane');
        grid.append(cell);
      }
      row.append(heading, grid); $('phase-rows').append(row);
    }
    $('visible-count').textContent = `${visible.length} of ${tasks.length} tasks`;
    $('empty-map').hidden = visible.length > 0;
    queueDraw();
  }
  function render() {
    const done = tasks.filter(task => status(task) === 'done').length, percentage = Math.round(done / (tasks.length || 1) * 100);
    $('progress-label').textContent = `${done} of ${tasks.length} tasks manually complete`;
    $('progress-percent').textContent = `${percentage}%`;
    $('progress-fill').style.width = `${percentage}%`;
    document.querySelector('[role=progressbar]').setAttribute('aria-valuenow', percentage);
    renderStarts(); renderMap();
  }
  function queueDraw() { cancelAnimationFrame(drawFrame); drawFrame = requestAnimationFrame(drawConnections); }
  function drawConnections() {
    const svg = $('connections'); svg.replaceChildren();
    if (window.innerWidth <= 760) return;
    const ns = 'http://www.w3.org/2000/svg', bounds = $('work-map').getBoundingClientRect(), cards = new Map();
    document.querySelectorAll('.task-card').forEach(card => cards.set(card.dataset.taskId, card.getBoundingClientRect()));
    const defs = document.createElementNS(ns, 'defs'), marker = document.createElementNS(ns, 'marker'), arrow = document.createElementNS(ns, 'path');
    for (const [key, value] of Object.entries({ id: 'arrow', viewBox: '0 0 6 6', refX: '5', refY: '3', markerWidth: '5', markerHeight: '5', orient: 'auto' })) marker.setAttribute(key, value);
    arrow.setAttribute('d', 'M 0 0 L 6 3 L 0 6 Z'); arrow.setAttribute('fill', '#b9a28d'); marker.append(arrow); defs.append(marker); svg.append(defs);
    svg.setAttribute('viewBox', `0 0 ${bounds.width} ${bounds.height}`);
    for (const task of tasks) {
      const target = cards.get(task.id); if (!target) continue;
      dependencies(task).forEach((id, index) => {
        const source = cards.get(id); if (!source) return;
        const x1 = source.left + source.width / 2 - bounds.left, y1 = source.bottom - bounds.top + 1;
        const x2 = target.left + target.width / 2 - bounds.left + (index - (dependencies(task).length - 1) / 2) * 8, y2 = target.top - bounds.top - 3;
        const path = document.createElementNS(ns, 'path');
        if (Math.abs(x1 - x2) < 24 && y2 > y1) {
          const channel = source.right - bounds.left + 8 + index * 3;
          path.setAttribute('d', `M ${x1} ${y1} C ${x1} ${y1 + 12},${channel} ${y1 + 12},${channel} ${y1 + 22} L ${channel} ${y2 - 20} C ${channel} ${y2 - 10},${x2} ${y2 - 12},${x2} ${y2}`);
        } else {
          const curve = Math.max(22, Math.abs(y2 - y1) * .45);
          path.setAttribute('d', `M ${x1} ${y1} C ${x1} ${y1 + curve},${x2} ${y2 - curve},${x2} ${y2}`);
        }
        path.setAttribute('class', `dependency-path${record(id).status === 'done' ? ' completed' : ''}`);
        path.setAttribute('marker-end', 'url(#arrow)'); svg.append(path);
      });
    }
  }
  function openTask(id) {
    const task = byId.get(id); if (!task) return;
    selected = id;
    $('task-kicker').textContent = `${id} / Phase ${task.phase}`;
    $('task-title').textContent = task.title; $('task-summary').textContent = task.summary;
    $('task-badges').replaceChildren(...[task.owner, task.priority, labels[status(task)], ...(task.optional ? ['Optional'] : [])].map((text, index) => el('span', `badge${index === 0 ? ' emphasis' : ''}`, text)));
    $('task-deps').replaceChildren();
    if (!dependencies(task).length) $('task-deps').append(el('p', '', 'None. This task can begin immediately.'));
    dependencies(task).forEach(dep => {
      const prerequisite = byId.get(dep), button = el('button', '', `${dep} · ${prerequisite?.title || 'Missing task'} — ${prerequisite ? labels[status(prerequisite)] : 'Unavailable'}`);
      button.type = 'button'; button.disabled = !prerequisite; button.addEventListener('click', () => openTask(dep)); $('task-deps').append(button);
    });
    for (const [target, field] of [['task-deliverables', 'deliverables'], ['task-acceptance', 'acceptance']]) $(target).replaceChildren(...list(task[field]).map(value => el('li', '', value)));
    $('task-prompt').value = task.prompt || ''; $('prompt-source').textContent = task.source ? `Prompt source: ${task.source}` : '';
    const item = record(id); $('task-status').value = item.status; $('task-notes').value = item.notes; $('task-evidence').value = item.evidence;
    const ready = depsDone(task);
    for (const option of $('task-status').options) option.disabled = option.value !== 'todo' && !ready;
    $('completion-hint').textContent = !ready ? 'Blocked: complete each prerequisite first. Notes and evidence can still be saved.' : item.needsRecheck ? 'A prerequisite was reopened. Recheck this work before recording it complete again.' : 'Reopening this task also reopens dependent work for recheck.';
    $('form-error').textContent = ''; $('copy-prompt').textContent = 'Copy prompt';
    if (!$('task-dialog').open) { $('task-dialog').showModal(); document.body.classList.add('dialog-open'); }
    $('task-dialog').scrollTop = 0; $('close-dialog').focus();
  }
  $('close-dialog').addEventListener('click', () => $('task-dialog').close());
  $('task-dialog').addEventListener('close', () => { document.body.classList.remove('dialog-open'); selected = null; });
  $('progress-form').addEventListener('submit', event => {
    event.preventDefault(); const task = byId.get(selected); if (!task) return;
    const next = $('task-status').value, evidence = $('task-evidence').value.trim();
    if (next !== 'todo' && !depsDone(task)) { $('form-error').textContent = 'Complete every prerequisite before starting or completing this task.'; return; }
    if (next === 'done' && !evidence) { $('form-error').textContent = 'Add completion evidence before marking this task complete.'; $('task-evidence').focus(); return; }
    records[task.id] = { status: next, notes: $('task-notes').value, evidence, needsRecheck: next === 'todo' && record(task.id).needsRecheck === true };
    const reset = invalidate(), saved = persist(); render(); openTask(task.id);
    const message = `${saved ? 'Progress saved locally.' : 'Progress kept in this tab only; export before closing.'}${reset.length ? ` ${reset.join(', ')} reopened for prerequisite recheck; notes and evidence were preserved.` : ''}`;
    $('completion-hint').textContent = message; announce(message);
  });
  $('copy-prompt').addEventListener('click', async () => {
    try { if (!navigator.clipboard) throw new Error('Clipboard unavailable'); await navigator.clipboard.writeText($('task-prompt').value); $('copy-prompt').textContent = 'Copied'; }
    catch { $('task-prompt').focus(); $('task-prompt').select(); $('copy-prompt').textContent = 'Selected — press Ctrl/Cmd+C'; }
  });
  for (const id of ['owner-filter', 'status-filter', 'optional-filter']) $(id).addEventListener('change', renderMap);
  $('export-state').addEventListener('click', () => {
    const blob = new Blob([JSON.stringify({ version: data.version, exportedAt: new Date().toISOString(), snapshotCheckedAt: data.checkedAt, records }, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob), link = el('a'); link.href = url; link.download = `boom-roadmap-progress-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); announce('Progress exported. This file contains manually reported status, notes, and evidence.');
  });
  $('import-state').addEventListener('click', () => $('import-file').click());
  $('import-file').addEventListener('change', async event => {
    const file = event.target.files[0]; if (!file) return;
    try {
      if (file.size > 2000000) throw new Error('This progress file is too large (maximum 2 MB).');
      const imported = parseState(await file.text());
      if (!window.confirm('Replace this browser’s current progress with this file? Export your current progress first if you want to keep it.')) return;
      records = imported; const reset = invalidate(); const saved = persist(); render();
      announce(`Progress imported${saved ? ' and saved locally' : ' for this tab only; export before closing'}. ${reset.length ? `${reset.length} dependent task(s) reopened for recheck.` : 'Completion remains manually reported.'}`);
    } catch (error) { announce(`Import failed: ${error.message}`); }
    finally { event.target.value = ''; }
  });
  window.addEventListener('resize', queueDraw);
  if (typeof ResizeObserver !== 'undefined') new ResizeObserver(queueDraw).observe($('phase-rows'));
  render();
})();
