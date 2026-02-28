(function () {
  'use strict';

  // Ensure idempotency if this script is included multiple times.
  if (window.__CTFD_MODULES_ADMIN_CHALLENGES_PATCH_LOADED) return;
  window.__CTFD_MODULES_ADMIN_CHALLENGES_PATCH_LOADED = true;

  function findNonce(root) {
    try {
      var el = (root || document).querySelector('input[name="nonce"]');
      return el && el.value ? el.value : '';
    } catch (e) {
      return '';
    }
  }

  function currentChallengeId() {
    try {
      var m = window.location.pathname.match(/\/admin\/challenges\/(\d+)/);
      if (m && m[1]) return parseInt(m[1], 10);
    } catch (e) {}

    try {
      var el = document.querySelector('input[name="id"], input#challenge-id, input[name="challenge_id"]');
      if (el && el.value) return parseInt(el.value, 10);
    } catch (e) {}

    return null;
  }

  async function postJson(url, payload, root) {
    payload = payload || {};
    payload.nonce = payload.nonce || findNonce(root) || findNonce(document);

    // Prefer CTFd helper if present.
    try {
      if (window.CTFd && typeof window.CTFd.fetch === 'function') {
        return await window.CTFd.fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
          body: JSON.stringify(payload),
        });
      }
    } catch (e) {}

    var nonce = payload.nonce || '';
    return await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'CSRF-Token': nonce,
        'X-CSRFToken': nonce,
        'X-CSRF-Token': nonce,
      },
      body: JSON.stringify(payload),
    });
  }

  async function getJson(url) {
    try {
      if (window.CTFd && typeof window.CTFd.fetch === 'function') {
        var resp = await window.CTFd.fetch(url, {
          method: 'GET',
          headers: { Accept: 'application/json' },
        });
        if (!resp || !resp.ok) return null;
        return await resp.json();
      }
    } catch (e) {}

    try {
      var r = await fetch(url, {
        method: 'GET',
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      });
      if (!r.ok) return null;
      return await r.json();
    } catch (e) {
      return null;
    }
  }

  async function setChallengeModules(challengeId, moduleIds) {
    return await postJson('/api/v1/modules/assign', { challenge_id: challengeId, module_ids: moduleIds || [] });
  }

  async function getAssignedModuleIds(challengeId) {
    var payload = await getJson('/api/v1/modules/challenge/' + encodeURIComponent(String(challengeId)));
    try {
      if (!payload || payload.success !== true) return [];
      var data = payload.data || {};
      var out = [];

      if (Array.isArray(data.module_ids)) {
        for (var i = 0; i < data.module_ids.length; i++) {
          var id = parseInt(data.module_ids[i], 10);
          if (!isNaN(id)) out.push(id);
        }
      } else if (data.module_id != null && data.module_id !== '') {
        var mid = parseInt(data.module_id, 10);
        if (!isNaN(mid)) out.push(mid);
      }

      var seen = {};
      var unique = [];
      for (var j = 0; j < out.length; j++) {
        if (!seen[out[j]]) {
          seen[out[j]] = true;
          unique.push(out[j]);
        }
      }
      return unique;
    } catch (e) {
      return [];
    }
  }

  async function waitForChallengeId(maxMs) {
    var started = Date.now();
    while (Date.now() - started <= (maxMs || 3000)) {
      var cid = currentChallengeId();
      if (cid) return cid;
      await new Promise(function (resolve) {
        setTimeout(resolve, 120);
      });
    }
    return null;
  }

  function initChallengeFormPatch() {
    var sel = document.getElementById('ctfd-modules-module-select');
    if (!sel) return;
    var field = document.getElementById('ctfd-modules-module-field') || (sel.closest ? sel.closest('.form-group') : null);

    if (!sel.multiple) {
      sel.multiple = true;
      sel.setAttribute('multiple', 'multiple');
    }
    if (!sel.classList.contains('d-none')) sel.classList.add('d-none');

    for (var oi = 0; oi < sel.options.length; oi++) {
      var option = sel.options[oi];
      if (!option.dataset) continue;
      if (!option.dataset.name) {
        option.dataset.name = (option.textContent || '').trim();
      }
      if (!option.dataset.category) {
        var rawCategory = option.getAttribute('data-category');
        option.dataset.category = (rawCategory || 'No Category').trim() || 'No Category';
      }
    }

    var picker = document.getElementById('ctfd-modules-module-picker');
    if (!picker) {
      picker = document.createElement('select');
      picker.id = 'ctfd-modules-module-picker';
      picker.className = 'form-control';
      if (field) field.insertBefore(picker, sel);
    }

    var tagsRoot = document.getElementById('ctfd-modules-tags');
    if (!tagsRoot) {
      tagsRoot = document.createElement('div');
      tagsRoot.id = 'ctfd-modules-tags';
      tagsRoot.className = 'my-2';
      if (field) field.insertBefore(tagsRoot, sel);
    }

    var statusEl = document.getElementById('ctfd-modules-module-status');
    if (!statusEl) {
      statusEl = document.createElement('small');
      statusEl.id = 'ctfd-modules-module-status';
      statusEl.className = 'form-text text-muted mt-1';
      if (field) field.insertBefore(statusEl, sel);
    }

    function showStatus(message, isError) {
      if (!statusEl) return;
      statusEl.textContent = message || '';
      statusEl.className = 'form-text mt-1 ' + (isError ? 'text-danger' : 'text-muted');
    }

    if (sel.dataset.ctfdModulesWired === '1') return;
    sel.dataset.ctfdModulesWired = '1';
    var moduleStateIds = [];

    function normalizeIds(list) {
      if (!Array.isArray(list)) return [];
      var out = [];
      for (var i = 0; i < list.length; i++) {
        var id = parseInt(list[i], 10);
        if (!isNaN(id) && id > 0) out.push(id);
      }
      var seen = {};
      var unique = [];
      for (var j = 0; j < out.length; j++) {
        if (!seen[out[j]]) {
          seen[out[j]] = true;
          unique.push(out[j]);
        }
      }
      return unique;
    }

    function selectedModuleIds() {
      return normalizeIds(moduleStateIds);
    }

    function syncSelectSelection(ids) {
      var set = {};
      ids = normalizeIds(ids);
      for (var i = 0; i < ids.length; i++) set[ids[i]] = true;
      for (var j = 0; j < sel.options.length; j++) {
        var value = parseInt(sel.options[j].value, 10);
        sel.options[j].selected = !!set[value];
      }
    }

    function moduleInfoList() {
      var rows = [];
      for (var i = 0; i < sel.options.length; i++) {
        var rowId = parseInt(sel.options[i].value, 10);
        if (isNaN(rowId) || rowId <= 0) continue;
        rows.push({
          id: rowId,
          name: ((sel.options[i].dataset && sel.options[i].dataset.name) || sel.options[i].textContent || '').trim() || String(rowId),
          category: ((sel.options[i].dataset && sel.options[i].dataset.category) || 'No Category').trim() || 'No Category',
        });
      }
      rows.sort(function (a, b) {
        var catCmp = a.category.localeCompare(b.category);
        if (catCmp !== 0) return catCmp;
        return a.name.localeCompare(b.name);
      });
      return rows;
    }

    function moduleNameById(moduleId) {
      for (var i = 0; i < sel.options.length; i++) {
        var value = parseInt(sel.options[i].value, 10);
        if (value === moduleId) {
          return (sel.options[i].dataset && sel.options[i].dataset.name) || sel.options[i].textContent || String(moduleId);
        }
      }
      return String(moduleId);
    }

    function renderPickerOptions() {
      if (!picker) return;
      picker.innerHTML = '';

      var firstOption = document.createElement('option');
      firstOption.value = '';
      firstOption.textContent = '— Select module —';
      picker.appendChild(firstOption);

      var selectedSet = {};
      var ids = selectedModuleIds();
      for (var i = 0; i < ids.length; i++) selectedSet[ids[i]] = true;

      var rows = moduleInfoList();
      var groups = {};
      var groupOrder = [];
      for (var j = 0; j < rows.length; j++) {
        var category = rows[j].category;
        if (!groups[category]) {
          groups[category] = [];
          groupOrder.push(category);
        }
        groups[category].push(rows[j]);
      }

      for (var g = 0; g < groupOrder.length; g++) {
        var groupName = groupOrder[g];
        var optgroup = document.createElement('optgroup');
        optgroup.label = groupName;

        var groupRows = groups[groupName] || [];
        for (var k = 0; k < groupRows.length; k++) {
          var option = document.createElement('option');
          option.value = String(groupRows[k].id);
          option.textContent = groupRows[k].name;
          if (selectedSet[groupRows[k].id]) option.disabled = true;
          optgroup.appendChild(option);
        }

        picker.appendChild(optgroup);
      }

      picker.value = '';
    }

    function renderTags() {
      if (!tagsRoot) return;
      tagsRoot.innerHTML = '';

      var ids = selectedModuleIds();
      for (var i = 0; i < ids.length; i++) {
        var id = ids[i];
        var badge = document.createElement('span');
        badge.className = 'badge badge-primary mx-1 challenge-tag';

        var label = document.createElement('span');
        label.textContent = moduleNameById(id);
        badge.appendChild(label);

        var remove = document.createElement('a');
        remove.className = 'btn-fa delete-tag';
        remove.textContent = ' ×';
        remove.href = 'javascript:void(0)';
        remove.setAttribute('data-module-id', String(id));
        remove.addEventListener('click', function (e) {
          var raw = e && e.currentTarget ? e.currentTarget.getAttribute('data-module-id') : null;
          var moduleId = parseInt(raw, 10);
          if (isNaN(moduleId)) return;
          var next = selectedModuleIds().filter(function (x) {
            return x !== moduleId;
          });
          setSelectedModuleIds(next, true);
        });
        badge.appendChild(remove);

        tagsRoot.appendChild(badge);
      }
    }

    function setSelectedModuleIds(ids, emitChange) {
      moduleStateIds = normalizeIds(ids);
      syncSelectSelection(moduleStateIds);
      renderPickerOptions();
      renderTags();
      if (emitChange) {
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      }
    }

    function parsePendingIds(raw) {
      if (!raw) return [];
      try {
        var parsed = JSON.parse(raw);
        return normalizeIds(parsed);
      } catch (e) {
        var single = parseInt(raw, 10);
        return isNaN(single) ? [] : [single];
      }
    }

    document.addEventListener(
      'submit',
      function (e) {
        try {
          var form = e && e.target ? e.target : null;
          if (!form || form.tagName !== 'FORM') return;
          if (!form.contains(sel)) return;
          window.localStorage.setItem('ctfd_modules_pending_module_ids', JSON.stringify(selectedModuleIds()));
        } catch (err) {}
      },
      true
    );

    var pending = [];
    try {
      pending = parsePendingIds(window.localStorage.getItem('ctfd_modules_pending_module_ids'));
      if (!pending.length) {
        pending = parsePendingIds(window.localStorage.getItem('ctfd_modules_pending_module_id'));
      }
      window.localStorage.removeItem('ctfd_modules_pending_module_id');
    } catch (e) {}

    var initialIds = pending.length
      ? pending
      : (function () {
          var current = [];
          for (var si = 0; si < sel.options.length; si++) {
            if (!sel.options[si].selected) continue;
            var sid = parseInt(sel.options[si].value, 10);
            if (!isNaN(sid)) current.push(sid);
          }
          return current;
        })();
    setSelectedModuleIds(initialIds, false);

    if (picker) {
      picker.addEventListener('change', function () {
        var picked = parseInt(picker.value, 10);
        if (isNaN(picked) || picked <= 0) {
          picker.value = '';
          return;
        }
        var next = selectedModuleIds();
        if (next.indexOf(picked) === -1) next.push(picked);
        setSelectedModuleIds(next, true);
      });
    }

    var challengeId = currentChallengeId();

    async function saveSelection(cid) {
      if (!cid) return false;
      try {
        var response = await setChallengeModules(cid, selectedModuleIds());
        if (!response || !response.ok) {
          showStatus('Failed to save modules', true);
          return false;
        }
        var payload = null;
        try {
          payload = await response.json();
        } catch (_) {
          payload = null;
        }
        if (payload && payload.success === false) {
          showStatus('Failed to save modules', true);
          return false;
        }
        showStatus('Modules saved', false);
        return true;
      } catch (e) {
        showStatus('Failed to save modules', true);
        return false;
      }
    }

    sel.addEventListener('change', async function () {
      moduleStateIds = (function () {
        var ids = [];
        for (var i = 0; i < sel.options.length; i++) {
          if (!sel.options[i].selected) continue;
          var id = parseInt(sel.options[i].value, 10);
          if (!isNaN(id)) ids.push(id);
        }
        return normalizeIds(ids);
      })();
      renderPickerOptions();
      renderTags();
      if (!challengeId) challengeId = await waitForChallengeId(4000);
      if (!challengeId) return;
      void saveSelection(challengeId);
    });

    (async function bootstrapSelection() {
      if (!challengeId) challengeId = await waitForChallengeId(4000);
      if (!challengeId) return;

      if (pending.length) {
        await saveSelection(challengeId);
        try {
          window.localStorage.removeItem('ctfd_modules_pending_module_ids');
        } catch (e) {}
        return;
      }

      if (!selectedModuleIds().length) {
        var assignedIds = await getAssignedModuleIds(challengeId);
        if (assignedIds.length) {
          setSelectedModuleIds(assignedIds, false);
        }
      }
    })();
  }

  function selectedChallengeIds() {
    var selectors = [
      'table input[type="checkbox"][name="challenge_id"]:checked',
      'table input[type="checkbox"][name="challenge_ids[]"]:checked',
      'table input[type="checkbox"][data-challenge-id]:checked',
      'table input[type="checkbox"].challenge-checkbox:checked',
      'table input[type="checkbox"]:checked',
    ];

    var nodes = [];
    for (var i = 0; i < selectors.length; i++) {
      try {
        nodes = Array.prototype.slice.call(document.querySelectorAll(selectors[i]));
        if (nodes && nodes.length) break;
      } catch (e) {}
    }

    var ids = [];
    nodes.forEach(function (n) {
      var v = null;
      try {
        if (n.dataset && n.dataset.challengeId) v = n.dataset.challengeId;
        if (!v) v = n.value;
      } catch (e) {}

      var cid = parseInt(v, 10);
      if (!isNaN(cid) && cid > 0) ids.push(cid);
    });

    var seen = {};
    var out = [];
    ids.forEach(function (cid) {
      if (!seen[cid]) {
        seen[cid] = true;
        out.push(cid);
      }
    });

    return out;
  }

  function findBulkModal() {
    try {
      var modals = Array.prototype.slice.call(document.querySelectorAll('.modal'));
      for (var i = 0; i < modals.length; i++) {
        var id = (modals[i].getAttribute('id') || '').toLowerCase();
        var text = (modals[i].textContent || '').toLowerCase();
        if (id.indexOf('bulk') !== -1 || id.indexOf('edit') !== -1) {
          // Heuristic: bulk/edit modal usually contains category/state/visibility fields
          if (text.indexOf('category') !== -1 || text.indexOf('state') !== -1 || text.indexOf('visibility') !== -1) {
            return modals[i];
          }
        }
      }
    } catch (e) {}

    return null;
  }

  function ensureBulkStatus(modal) {
    var body = modal.querySelector('.modal-body') || modal;
    var el = modal.querySelector('#ctfd-modules-bulk-status');
    if (el) return el;
    el = document.createElement('div');
    el.id = 'ctfd-modules-bulk-status';
    el.className = 'alert mt-3 d-none';
    body.appendChild(el);
    return el;
  }

  function loadBulkModuleOptionsHtml() {
    try {
      var tpl = document.getElementById('ctfd-modules-bulk-module-options');
      if (!tpl) return '';
      // template.content isn't available in very old browsers, but CTFd admin runs modern ones.
      return (tpl.innerHTML || '').trim();
    } catch (e) {
      return '';
    }
  }

  function ensureBulkModuleField(modal) {
    if (!modal) return null;
    var existing = modal.querySelector('#ctfd-modules-bulk-module-select');
    if (existing) return existing;

    var body = modal.querySelector('.modal-body') || modal;
    var wrap = document.createElement('div');
    wrap.className = 'form-group';

    var optionsHtml = loadBulkModuleOptionsHtml();
    wrap.innerHTML =
      '<label class="mb-1">Module</label>' +
      '<select class="form-control" id="ctfd-modules-bulk-module-select">' +
      '<option value="">— No change —</option>' +
      '<option value="__unassign__">— Unassign —</option>' +
      (optionsHtml || '') +
      '</select>' +
      '<small class="form-text text-muted">Selecting module adds mapping. Unassign removes all module mappings.</small>';

    body.appendChild(wrap);
    return modal.querySelector('#ctfd-modules-bulk-module-select');
  }

  function attachBulkSubmit(modal) {
    var form = modal.querySelector('form');
    if (!form || form.dataset.ctfdModulesHooked === '1') return;
    form.dataset.ctfdModulesHooked = '1';

    form.addEventListener(
      'submit',
      async function (e) {
        // prevent recursion
        if (form.dataset.ctfdModulesHandled === '1') {
          form.dataset.ctfdModulesHandled = '0';
          return;
        }

        var sel = modal.querySelector('#ctfd-modules-bulk-module-select');
        if (!sel) return;

        var v = sel.value || '';
        if (!v) {
          return; // no change
        }

        var ids = selectedChallengeIds();
        if (!ids.length) {
          return; // let core handle its own validation
        }

        e.preventDefault();

        var status = ensureBulkStatus(modal);
        status.className = 'alert alert-info mt-3';
        status.textContent = 'Applying module mapping…';
        status.classList.remove('d-none');

        var payload = { challenge_ids: ids };
        if (v === '__unassign__') {
          payload.module_id = '';
        } else {
          payload.module_id = v;
        }

        try {
          var r = await postJson('/api/v1/modules/bulk/assign', payload, form);
          if (!r || r.status !== 200) {
            status.className = 'alert alert-danger mt-3';
            status.textContent = 'Failed to apply module (HTTP ' + (r ? r.status : '?') + ')';
            return;
          }
        } catch (err) {
          status.className = 'alert alert-danger mt-3';
          status.textContent = 'Failed to apply module';
          return;
        }

        // Allow core bulk edit to proceed
        sel.value = '';
        form.dataset.ctfdModulesHandled = '1';
        form.submit();
      },
      true
    );
  }

  function initBulkPatch() {
    var modal = findBulkModal();
    if (!modal) return;
    ensureBulkModuleField(modal);
    attachBulkSubmit(modal);
  }

  document.addEventListener('DOMContentLoaded', function () {
    initChallengeFormPatch();
    initBulkPatch();
  });

  // Bootstrap modal show hook
  document.addEventListener(
    'shown.bs.modal',
    function () {
      initBulkPatch();
    },
    true
  );
})();
