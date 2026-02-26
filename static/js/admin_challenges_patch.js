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

  async function assignModule(challengeId, moduleId) {
    return await postJson('/api/v1/modules/assign', { challenge_id: challengeId, module_id: moduleId });
  }

  async function unassignModule(challengeId) {
    return await postJson('/api/v1/modules/unassign', { challenge_id: challengeId });
  }

  async function getAssignedModuleId(challengeId) {
    var payload = await getJson('/api/v1/modules/challenge/' + encodeURIComponent(String(challengeId)));
    try {
      if (!payload || payload.success !== true) return null;
      var data = payload.data || {};
      if (data.module_id == null || data.module_id === '') return null;
      var mid = parseInt(data.module_id, 10);
      return isNaN(mid) ? null : mid;
    } catch (e) {
      return null;
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

    // Prevent double-wiring.
    if (sel.dataset.ctfdModulesWired === '1') return;
    sel.dataset.ctfdModulesWired = '1';

    // Save pending selection on create; apply on next load (update page).
    document.addEventListener('submit', function (e) {
      try {
        var form = e && e.target ? e.target : null;
        if (!form || form.tagName !== 'FORM') return;
        if (!form.contains(sel)) return;
        window.localStorage.setItem('ctfd_modules_pending_module_id', sel.value || '');
      } catch (err) {}
    }, true);

    var pending = null;
    try {
      pending = window.localStorage.getItem('ctfd_modules_pending_module_id');
      if (pending === '') {
        window.localStorage.removeItem('ctfd_modules_pending_module_id');
        pending = null;
      }
      if (pending && !sel.value) sel.value = pending;
    } catch (e) {}

    var challengeId = currentChallengeId();

    function selectedModuleId() {
      if (!sel.value) return null;
      var v = parseInt(sel.value, 10);
      return isNaN(v) ? null : v;
    }

    async function saveSelection(cid) {
      if (!cid) return false;
      try {
        var moduleId = selectedModuleId();
        if (!moduleId) {
          await unassignModule(cid);
        } else {
          await assignModule(cid, moduleId);
        }
        return true;
      } catch (e) {
        return false;
      }
    }

    sel.addEventListener('change', async function () {
      if (!challengeId) challengeId = await waitForChallengeId(4000);
      if (!challengeId) return;
      void saveSelection(challengeId);
    });

    (async function bootstrapSelection() {
      if (!challengeId) challengeId = await waitForChallengeId(4000);
      if (!challengeId) return;

      // create -> redirect-to-edit flow
      if (pending) {
        // keep user's selected module and persist mapping once we have challenge id
        if (!sel.value) sel.value = pending;
        await saveSelection(challengeId);
        try {
          window.localStorage.removeItem('ctfd_modules_pending_module_id');
        } catch (e) {}
        return;
      }

      // edit flow: pull current mapping from backend when template can't preselect it
      if (!sel.value) {
        var assignedId = await getAssignedModuleId(challengeId);
        if (assignedId) sel.value = String(assignedId);
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
      '<small class="form-text text-muted">No change keeps current module. Unassign removes module.</small>';

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
        status.textContent = 'Applying module…';
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
