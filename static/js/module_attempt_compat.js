  // Автоматически обновлять solves (legacy pixo)
  function updateSolves(challengeId) {
    try {
      if (typeof window.getSolves === 'function') {
        window.getSolves(challengeId);
      }
    } catch (e) {}
  }
(function () {
  'use strict';

  function getUiTheme() {
    try {
      var t = (window.CTFD_MODULES_UI_THEME || '').toString().trim().toLowerCase();
      if (t) return t;
    } catch (e) {}
    return 'auto';
  }

  function shouldApplyPixoShims(root) {
    var t = getUiTheme();
    if (t === 'pixo') return true;
    if (t === 'core-beta') return false;

    // auto: be conservative to avoid breaking non-PIXO themes.
    return false;
  }

  function normalizePixoModalUi(root) {
    try {
      root = root || document;

      var input = root.querySelector('#challenge-input');
      if (input) {
        if (!input.classList.contains('challenge-input')) input.classList.add('challenge-input');
        // PIXO expects bootstrap styling
        if (!input.classList.contains('form-control')) input.classList.add('form-control');
      }

      var btn = root.querySelector('#challenge-submit');
      if (btn) {
        if (!btn.classList.contains('challenge-submit')) btn.classList.add('challenge-submit');
        if (!btn.classList.contains('btn')) btn.classList.add('btn');
        if (!btn.classList.contains('btn-md')) btn.classList.add('btn-md');
        if (!btn.classList.contains('btn-outline-secondary')) btn.classList.add('btn-outline-secondary');
        if (!btn.classList.contains('float-right')) btn.classList.add('float-right');
      }
    } catch (e) {}
  }

  function findNonce(root) {
    try {
      var el = (root || document).querySelector('input[name="nonce"]');
      return el && el.value ? el.value : '';
    } catch (e) {
      // fall through
    }

    // Common meta tags across themes/builds
    try {
      var m = document.querySelector('meta[name="csrf-token"], meta[name="csrfToken"], meta[name="csrf_nonce"], meta[name="nonce"]');
      var v = m ? (m.getAttribute('content') || '') : '';
      if (v) return v;
    } catch (e) {}

    // CTFd globals (varies by version)
    try {
      if (window.CTFd && window.CTFd.config && window.CTFd.config.csrfNonce) return window.CTFd.config.csrfNonce;
    } catch (e) {}
    try {
      if (window.init && window.init.nonce) return window.init.nonce;
    } catch (e) {}

    return '';
  }

  function findChallengeId(root) {
    try {
      var el = (root || document).querySelector('input[name="challenge_id"], input[name="id"], input#challenge-id');
      if (el && el.value) return parseInt(el.value, 10);
    } catch (e) {}

    try {
      if (window.CTFD_MODULES_ACTIVE_CHALLENGE_ID) return parseInt(window.CTFD_MODULES_ACTIVE_CHALLENGE_ID, 10);
    } catch (e) {}

    return null;
  }

  function findSubmission(root) {
    try {
      var el = (root || document).querySelector(
        'input[name="submission"], textarea[name="submission"], input#submission,' +
        'input[name="answer"], textarea[name="answer"], input#challenge-input, textarea#challenge-input'
      );
      return el ? (el.value || '') : '';
    } catch (e) {
      return '';
    }
  }

  function clearSubmissionInputs(root) {
    try {
      var fields = (root || document).querySelectorAll(
        'input[name="submission"], textarea[name="submission"], input#submission,' +
        'input[name="answer"], textarea[name="answer"], input#challenge-input, textarea#challenge-input'
      );
      if (!fields || !fields.length) return;
      fields.forEach(function (el) {
        try {
          el.value = '';
        } catch (_) {}
      });
    } catch (e) {}
  }

  function setResult(root, kind, text) {
    try {
      // PIXO / core themes: reuse existing notification UI if present.
      try {
        var notif = (root || document).querySelector('#result-notification');
        var msgEl = (root || document).querySelector('#result-message');
        if (notif && msgEl) {
          msgEl.textContent = text || '';
          // Use Bootstrap's built-in fade/show for smooth appearance.
          notif.style.display = '';
          notif.className =
            'alert alert-dismissable text-center w-100 fade ' +
            (kind === 'success' ? 'alert-success' : kind === 'warning' ? 'alert-warning' : 'alert-danger');

          // Restart fade-in even if previously shown.
          try {
            notif.classList.remove('show');
            void notif.offsetWidth;
          } catch (_) {}
          requestAnimationFrame(function () {
            try {
              notif.classList.add('show');
            } catch (_) {}
          });
          // Auto-dismiss after 2.5s (fade out, then hide)
          setTimeout(function () {
            try {
              notif.classList.remove('show');
              setTimeout(function () {
                notif.style.display = 'none';
              }, 300);
            } catch (_) {}
          }, 2500);
          return;
        }
      } catch (e) {}

      var container = (root || document).querySelector('#ctfd-modules-attempt-result');
      if (!container) {
        container = document.createElement('div');
        container.id = 'ctfd-modules-attempt-result';
        container.className = 'my-2';
        var modalBody = (root || document).querySelector('.modal-body') || (root || document);
        modalBody.insertBefore(container, modalBody.firstChild);
      }
      container.innerHTML = '';

      var div = document.createElement('div');
      div.className =
        'alert fade ' +
        (kind === 'success' ? 'alert-success' : kind === 'warning' ? 'alert-warning' : 'alert-danger');
      div.textContent = text || '';
      container.appendChild(div);

      // Fade in smoothly, then auto-dismiss after 2.5s.
      requestAnimationFrame(function () {
        try {
          div.classList.add('show');
        } catch (_) {}
      });
      setTimeout(function () {
        try {
          div.classList.remove('show');
          setTimeout(function () {
            div.style.display = 'none';
          }, 300);
        } catch (_) {}
      }, 2500);
    } catch (e) {
      // last resort
      try { alert(text); } catch (_) {}
    }
  }

  function ensureTabFade(modal) {
    try {
      var panes = (modal || document).querySelectorAll('.tab-pane');
      for (var i = 0; i < panes.length; i++) {
        // If theme didn't include fade, add it for smoother transitions.
        if (!panes[i].classList.contains('fade')) panes[i].classList.add('fade');
        // Bootstrap expects show on the active pane when using fade.
        if (panes[i].classList.contains('active') && !panes[i].classList.contains('show')) {
          panes[i].classList.add('show');
        }
      }
    } catch (e) {}
  }

  function showBootstrapTab(tabEl) {
    // Prefer official Bootstrap APIs if present (CTFd default behavior).
    try {
      if (window.bootstrap && window.bootstrap.Tab) {
        window.bootstrap.Tab.getOrCreateInstance(tabEl).show();
        return true;
      }
    } catch (e) {}

    // Bootstrap 4 + jQuery
    try {
      if (window.jQuery && window.jQuery.fn && typeof window.jQuery.fn.tab === 'function') {
        window.jQuery(tabEl).tab('show');
        return true;
      }
    } catch (e) {}

    return false;
  }

  function manualTabFallback(tabEl) {
    try {
      var targetSel =
        tabEl.getAttribute('data-bs-target') ||
        tabEl.getAttribute('data-target') ||
        tabEl.getAttribute('href') ||
        tabEl.getAttribute('data-href');
      if (!targetSel || targetSel.charAt(0) !== '#') return false;

      var container = tabEl.closest('.nav') || tabEl.parentElement;
      if (container) {
        var tabs = container.querySelectorAll('[data-toggle="tab"], [data-bs-toggle="tab"], a[href^="#"], button[data-bs-target], button[data-target]');
        for (var i = 0; i < tabs.length; i++) {
          tabs[i].classList.remove('active');
          try {
            tabs[i].setAttribute('aria-selected', 'false');
          } catch (_) {}
        }
      }
      tabEl.classList.add('active');
      try {
        tabEl.setAttribute('aria-selected', 'true');
      } catch (_) {}

      var pane = document.querySelector(targetSel);
      if (!pane) return true;

      var paneContainer = pane.parentElement;
      if (paneContainer) {
        var panes = paneContainer.querySelectorAll('.tab-pane');
        for (var j = 0; j < panes.length; j++) {
          panes[j].classList.remove('active');
          panes[j].classList.remove('show');
        }
      }
      pane.classList.add('active');
      if (!pane.classList.contains('fade')) pane.classList.add('fade');
      // Match Bootstrap behavior: activate first, then add `show` on next frame.
      requestAnimationFrame(function () {
        try {
          pane.classList.add('show');
        } catch (_) {}
      });
      return true;
    } catch (e) {
      return false;
    }
  }

  function hideModalWindow(modal) {
    if (!modal) return false;

    try {
      if (window.bootstrap && window.bootstrap.Modal) {
        window.bootstrap.Modal.getOrCreateInstance(modal).hide();
        return true;
      }
    } catch (_) {}

    try {
      if (window.jQuery && typeof window.jQuery.fn.modal === 'function') {
        window.jQuery(modal).modal('hide');
        return true;
      }
    } catch (_) {}

    try {
      modal.classList.remove('show');
      modal.setAttribute('aria-hidden', 'true');
      modal.style.display = 'none';
      document.body.classList.remove('modal-open');
      if (document.body && document.body.style) {
        document.body.style.removeProperty('padding-right');
      }
      var backdrops = document.querySelectorAll('.modal-backdrop');
      for (var i = 0; i < backdrops.length; i++) {
        try {
          backdrops[i].remove();
        } catch (_) {}
      }
      return true;
    } catch (_) {}

    return false;
  }

  function formatRelativeFromNow(dateObj) {
    try {
      var now = Date.now();
      var ts = dateObj.getTime();
      if (isNaN(ts)) return '';
      var deltaSec = Math.round((now - ts) / 1000);
      var isFuture = deltaSec < 0;
      var absSec = Math.abs(deltaSec);

      if (!isFuture && absSec < 5) return 'just now';

      var units = [
        { name: 'year', sec: 31536000 },
        { name: 'month', sec: 2592000 },
        { name: 'day', sec: 86400 },
        { name: 'hour', sec: 3600 },
        { name: 'minute', sec: 60 },
        { name: 'second', sec: 1 },
      ];

      for (var i = 0; i < units.length; i++) {
        var unit = units[i];
        if (absSec >= unit.sec || unit.name === 'second') {
          var value = Math.floor(absSec / unit.sec) || 1;
          var label = value + ' ' + unit.name + (value === 1 ? '' : 's');
          return isFuture ? ('in ' + label) : (label + ' ago');
        }
      }
    } catch (_) {}
    return '';
  }

  function formatSolveDate(raw) {
    try {
      if (window.dayjs && typeof window.dayjs === 'function') {
        var dx = window.dayjs(raw);
        if (dx && typeof dx.fromNow === 'function') {
          return dx.fromNow();
        }
      }
    } catch (_) {}
    try {
      var d = new Date(raw);
      if (!isNaN(d.getTime())) {
        var rel = formatRelativeFromNow(d);
        if (rel) return rel;
      }
    } catch (_) {}
    return raw || '';
  }

  function extractSolvesList(payload) {
    try {
      if (Array.isArray(payload)) return payload;
      if (payload && Array.isArray(payload.data)) return payload.data;
      if (payload && payload.data && Array.isArray(payload.data.data)) return payload.data.data;
      if (payload && payload.data && payload.data.solves && Array.isArray(payload.data.solves)) return payload.data.solves;
    } catch (_) {}
    return null;
  }

  async function fetchSolvesList(challengeId) {
    try {
      if (window.CTFd && window.CTFd.api && typeof window.CTFd.api.get_challenge_solves === 'function') {
        var apiResp = await window.CTFd.api.get_challenge_solves({ challengeId: challengeId });
        var fromApi = extractSolvesList(apiResp);
        if (fromApi) return { ok: true, list: fromApi };
      }
    } catch (_) {}

    try {
      var url = '/api/v1/challenges/' + encodeURIComponent(String(challengeId)) + '/solves';
      var resp = await fetch(url, {
        method: 'GET',
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      });
      if (!resp.ok) return { ok: false, list: [] };
      var json = await resp.json();
      var fromFetch = extractSolvesList(json);
      return { ok: true, list: fromFetch || [] };
    } catch (_) {
      return { ok: false, list: [] };
    }
  }

  function solveName(row) {
    try {
      if (row && row.name) return String(row.name);
      if (row && row.account && row.account.name) return String(row.account.name);
      if (row && row.user && row.user.name) return String(row.user.name);
      if (row && row.team && row.team.name) return String(row.team.name);
    } catch (_) {}
    return '';
  }

  function solveDate(row) {
    try {
      if (row && row.date) return row.date;
      if (row && row.created) return row.created;
      if (row && row.created_at) return row.created_at;
    } catch (_) {}
    return '';
  }

  function solveUrl(row) {
    try {
      if (row && row.account_url) return String(row.account_url);
      if (row && row.account && row.account.url) return String(row.account.url);
    } catch (_) {}
    return '';
  }

  function findSolvesTarget(modal) {
    try {
      return (
        (modal || document).querySelector('#challenge-solves-names') ||
        (modal || document).querySelector('#solves tbody') ||
        (modal || document).querySelector('.challenge-solves-names')
      );
    } catch (_) {
      return null;
    }
  }

  function setSolvesLabel(modal, count) {
    try {
      var links = (modal || document).querySelectorAll('.challenge-solves');
      for (var i = 0; i < links.length; i++) {
        links[i].textContent = String(count) + ' Solves';
      }
    } catch (_) {}
  }

  function renderSolvesFallback(modal, solves) {
    if (!modal) return;
    var list = Array.isArray(solves) ? solves : [];
    setSolvesLabel(modal, list.length);

    var box = findSolvesTarget(modal);
    if (!box) return;

    box.innerHTML = '';
    for (var i = 0; i < list.length; i++) {
      var row = list[i] || {};
      var tr = document.createElement('tr');

      var tdName = document.createElement('td');
      var name = solveName(row);
      var href = solveUrl(row);
      if (href) {
        var a = document.createElement('a');
        a.href = href;
        a.textContent = name;
        tdName.appendChild(a);
      } else {
        tdName.textContent = name;
      }

      var tdDate = document.createElement('td');
      tdDate.textContent = formatSolveDate(solveDate(row));

      tr.appendChild(tdName);
      tr.appendChild(tdDate);
      box.appendChild(tr);
    }
  }

  function callThemeGetSolves(challengeId) {
    try {
      var fn = window.getSolves;
      if (typeof fn === 'function' && !fn.__ctfdModulesShim) {
        return fn(challengeId);
      }
    } catch (_) {}
    return null;
  }

  function solvesKey(challengeId) {
    try {
      return String(parseInt(challengeId, 10));
    } catch (_) {
      return String(challengeId || '');
    }
  }

  async function loadSolvesReliable(modal, challengeId) {
    if (!challengeId) return;
    var root = modal || document;
    var key = solvesKey(challengeId);

    try {
      // Prevent request spam: load solves only once per challenge open.
      // Mutation observers/tab clicks can fire multiple times while a modal is rendering.
      if (root.dataset && root.dataset.ctfdModulesSolvesLoadedFor === key) return;
      if (root.dataset && root.dataset.ctfdModulesSolvesLoadingFor === key) return;
      if (root.dataset) root.dataset.ctfdModulesSolvesLoadingFor = key;
    } catch (_) {}

    try {
      // Let theme/core implementation run first when available.
      var usedThemeLoader = false;
      try {
        var maybePromise = callThemeGetSolves(challengeId);
        if (maybePromise !== null && maybePromise !== undefined) {
          usedThemeLoader = true;
        }
        if (maybePromise && typeof maybePromise.then === 'function') {
          await maybePromise;
        }
      } catch (_) {}

      // Only use direct fetch fallback when no theme loader exists.
      if (!usedThemeLoader) {
        var fetched = await fetchSolvesList(challengeId);
        if (fetched && fetched.ok) {
          renderSolvesFallback(root, fetched.list || []);
        }
      }

      try {
        if (root.dataset) {
          root.dataset.ctfdModulesSolvesLoadedFor = key;
        }
      } catch (_) {}
    } finally {
      try {
        if (root.dataset && root.dataset.ctfdModulesSolvesLoadingFor === key) {
          delete root.dataset.ctfdModulesSolvesLoadingFor;
        }
      } catch (_) {}
    }
  }

  function clearSolvesLoadState(modal) {
    var root = modal || document;
    try {
      if (!root.dataset) return;
      delete root.dataset.ctfdModulesSolvesLoadedFor;
      delete root.dataset.ctfdModulesSolvesLoadingFor;
    } catch (_) {}
  }

  function currentChallengeKey(modal) {
    try {
      var cid = findChallengeId(modal || document);
      if (!cid) return '';
      return solvesKey(cid);
    } catch (_) {
      return '';
    }
  }

  function resolveCtfApiAttemptFn() {
    try {
      if (!window.CTFd || !window.CTFd.api) return null;
      var api = window.CTFd.api;

      // CTFd has changed naming across versions/builds; try common candidates.
      var candidates = [
        'post_challenge_attempt',
        'postChallengeAttempt',
        'post_challenges_attempt',
        'postChallengesAttempt',
        'postChallengeAttempts',
      ];

      for (var i = 0; i < candidates.length; i++) {
        var name = candidates[i];
        if (typeof api[name] === 'function') return api[name].bind(api);
      }
    } catch (e) {}
    return null;
  }

  async function requestAttempt(payload, nonce) {
    // 1) Prefer the official CTFd client API if present.
    try {
      var apiFn = resolveCtfApiAttemptFn();
      if (apiFn) {
        var apiResult = await apiFn(payload);
        // Some versions return a fetch Response; others may return JSON directly.
        if (apiResult && typeof apiResult.json === 'function') {
          var apiJson = null;
          try {
            apiJson = await apiResult.json();
          } catch (_) {
            apiJson = null;
          }
          return { ok: !!apiResult.ok, status: apiResult.status, json: apiJson };
        }
        return { ok: true, status: 200, json: apiResult };
      }
    } catch (e) {
      // fall through
    }

    // 2) Next best: CTFd.fetch (handles credentials/csrf in many builds).
    try {
      if (window.CTFd && typeof window.CTFd.fetch === 'function') {
        var resp = await window.CTFd.fetch('/api/v1/challenges/attempt', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
          body: JSON.stringify(payload),
        });
        var json = null;
        try {
          json = await resp.json();
        } catch (_) {
          json = null;
        }
        return { ok: !!resp.ok, status: resp.status, json: json };
      }
    } catch (e) {
      // fall through
    }

    // 3) Fallback: manual fetch + nonce.
    var fallbackResp = await fetch('/api/v1/challenges/attempt', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'CSRF-Token': nonce || '',
        'X-CSRFToken': nonce || '',
        'X-CSRF-Token': nonce || '',
      },
      body: JSON.stringify(payload),
    });

    var fallbackJson = null;
    try {
      fallbackJson = await fallbackResp.json();
    } catch (_) {
      fallbackJson = null;
    }
    return { ok: !!fallbackResp.ok, status: fallbackResp.status, json: fallbackJson };
  }

  async function postAttempt(challengeId, submission, nonce) {
    var payload = { challenge_id: challengeId, submission: submission };
    if (nonce) payload.nonce = nonce;
    return await requestAttempt(payload, nonce);
  }

  function tryRefresh(challengeId) {
    try {
      window.dispatchEvent(new CustomEvent('load-challenges'));
    } catch (e) {}
  }

  async function handleAttempt(root, e) {
    try {
      var modal = root || document;

      // Avoid double-submit (click + form submit) and concurrent requests.
      try {
        if (modal && modal.dataset && modal.dataset.ctfdModulesAttemptInFlight === '1') {
          return;
        }
        if (modal && modal.dataset) {
          modal.dataset.ctfdModulesAttemptInFlight = '1';
        }
      } catch (_) {}

      var submitBtn = null;
      try {
        submitBtn = modal.querySelector('#challenge-submit, .challenge-submit');
        if (submitBtn) submitBtn.disabled = true;
      } catch (_) {}

      var challengeId = findChallengeId(modal);
      var submission = findSubmission(modal);
      if (!challengeId) return;

      // If there is no recognizable input, don't interfere.
      if (!submission && !modal.querySelector('input[name="submission"], textarea[name="submission"], input#submission, input[name="answer"], textarea[name="answer"], input#challenge-input, textarea#challenge-input')) {
        return;
      }

      if (e && e.preventDefault) e.preventDefault();
      if (e && e.stopPropagation) e.stopPropagation();

      var nonce = findNonce(modal) || findNonce(document);

      var result = await postAttempt(challengeId, submission, nonce);
      var json = result ? result.json : null;

      if (!result || !result.ok || !json || json.success === false) {
        var msg = (json && (json.message || (json.data && json.data.message) || json.error)) || ('Flag submission failed (HTTP ' + (result ? result.status : '?') + ')');
        setResult(modal, 'danger', msg);
        return;
      }

      var status = (json.data && json.data.status) || '';
      var message = (json.data && json.data.message) || json.message || '';
      if (status === 'correct') {
        setResult(modal, 'success', message || 'Correct');
         updateSolves(challengeId);
        // Refresh the board/list, but don't immediately reload the modal view,
        // otherwise the result UI disappears due to x-html re-render.
        setTimeout(function () {
          tryRefresh(challengeId);
        }, 400);
      } else if (status === 'already_solved') {
        setResult(modal, 'warning', message || 'Already solved');
         updateSolves(challengeId);
        setTimeout(function () {
          tryRefresh(challengeId);
        }, 400);
      } else {
        setResult(modal, 'danger', message || 'Incorrect');
      }
    } catch (err) {
      try {
        setResult(root || document, 'danger', 'Flag submission failed');
      } catch (_) {}
    } finally {
      try {
        var modal2 = root || document;
        if (modal2 && modal2.dataset) {
          delete modal2.dataset.ctfdModulesAttemptInFlight;
        }
      } catch (_) {}
      try {
        clearSubmissionInputs(root || document);
      } catch (_) {}
      try {
        var modal3 = root || document;
        var btn = modal3 && modal3.querySelector ? modal3.querySelector('#challenge-submit, .challenge-submit') : null;
        if (btn) btn.disabled = false;
      } catch (_) {}
    }
  }

  function attach() {
    var modal = document.getElementById('challenge-window') || document.querySelector('#challenge-window');
    if (!modal) return;

    if (modal.dataset && modal.dataset.ctfdModulesAttemptHooked === '1') return;
    if (modal.dataset) modal.dataset.ctfdModulesAttemptHooked = '1';

    // Автоматически подгружать solves при каждом открытии challenge
    function autoLoadSolves() {
      try {
        var challengeId = findChallengeId(modal);
        if (challengeId) {
          var key = solvesKey(challengeId);
          if (modal.dataset && modal.dataset.ctfdModulesCurrentChallengeKey !== key) {
            clearSolvesLoadState(modal);
            modal.dataset.ctfdModulesCurrentChallengeKey = key;
          }
          void loadSolvesReliable(modal, challengeId);
        }
      } catch (_) {}
    }
    // При первом attach
    autoLoadSolves();
    // И при каждом изменении содержимого (Alpine x-html или legacy)
    try {
      var observer = new MutationObserver(function () {
        autoLoadSolves();
      });
      observer.observe(modal, { childList: true, subtree: true });
    } catch (_) {}
    // Normalize UI whenever the modal content changes (Alpine x-html / theme differences).
    try {
      // Ensure tab panes get smooth fade transitions after dynamic injection.
      ensureTabFade(modal);

      if (shouldApplyPixoShims(modal)) {
        normalizePixoModalUi(modal);
        var observer = new MutationObserver(function () {
          ensureTabFade(modal);
          if (shouldApplyPixoShims(modal)) normalizePixoModalUi(modal);
        });
        observer.observe(modal, { childList: true, subtree: true });
      } else {
        var observer2 = new MutationObserver(function () {
          ensureTabFade(modal);
        });
        observer2.observe(modal, { childList: true, subtree: true });
      }
    } catch (e) {}

    // Capture submits inside the modal and do the attempt ourselves.
    modal.addEventListener(
      'submit',
      async function (e) {
        try {
          var form = e.target;
          if (!form || form.tagName !== 'FORM') return;

          // Only handle forms that look like challenge submissions.
          var challengeId = findChallengeId(form) || findChallengeId(modal);
          var submission = findSubmission(form) || findSubmission(modal);
          if (!challengeId) return;

          // If the form doesn't have a submission field, don't interfere.
          if (!submission && !((form || {}).querySelector && form.querySelector('input[name="submission"], textarea[name="submission"], input#submission, input[name="answer"], textarea[name="answer"], input#challenge-input, textarea#challenge-input'))) {
            return;
          }

          // Route through the same logic so we consistently use CTFd.api/CTFd.fetch when available.
          await handleAttempt(modal, e);
        } catch (err) {
          try {
            setResult(document.getElementById('challenge-window'), 'danger', 'Flag submission failed');
          } catch (_) {}
        }
      },
      true
    );

    // core-beta: challenge modal HTML is injected via x-html, so bootstrap's data-api
    // may not always wire tab switching. Use the standard APIs on click.
    modal.addEventListener(
      'click',
      function (e) {
        try {
          var t = e.target;
          if (!t) return;
          var closeBtn = null;
          if (t.matches && t.matches('[data-bs-dismiss="modal"], [data-dismiss="modal"], .modal-header .btn-close, .modal-header .close')) {
            closeBtn = t;
          } else if (t.closest) {
            closeBtn = t.closest('[data-bs-dismiss="modal"], [data-dismiss="modal"], .modal-header .btn-close, .modal-header .close');
          }
          if (closeBtn) {
            e.preventDefault();
            e.stopPropagation();
            hideModalWindow(modal);
            return;
          }

          var tab = null;
          if (t.matches && (t.matches('[data-toggle="tab"], [data-bs-toggle="tab"]') || t.matches('.nav-link'))) {
            tab = t;
          } else if (t.closest) {
            tab = t.closest('[data-toggle="tab"], [data-bs-toggle="tab"], .nav-link');
          }
          if (!tab) return;

          // Heuristic: only treat as tab if it points to an in-page pane.
          var targetSel = tab.getAttribute('data-bs-target') || tab.getAttribute('data-target') || tab.getAttribute('href') || '';
          if (!targetSel || targetSel.charAt(0) !== '#') return;

          e.preventDefault();
          e.stopPropagation();

          if (!showBootstrapTab(tab)) {
            manualTabFallback(tab);
          }

          if ((tab.classList && tab.classList.contains('challenge-solves')) || targetSel === '#solves') {
            var challengeId2 = findChallengeId(modal);
            if (challengeId2) void loadSolvesReliable(modal, challengeId2);
          }
        } catch (err) {}
      },
      true
    );

    // PIXO / some themes: submit button may not be inside a <form>.
    modal.addEventListener(
      'click',
      function (e) {
        try {
          var t = e.target;
          if (!t) return;
           // Legacy solves click
           if (t.classList && t.classList.contains('challenge-solves')) {
             var challengeId = findChallengeId(modal);
             if (challengeId) void loadSolvesReliable(modal, challengeId);
           }
          var btn = null;
          if (t.matches && (t.matches('#challenge-submit') || t.matches('.challenge-submit'))) {
            btn = t;
          } else if (t.closest) {
            btn = t.closest('#challenge-submit, .challenge-submit');
          }
          if (!btn) return;
          void handleAttempt(modal, e);
        } catch (err) {}
      },
      true
    );

    // Enter key in the input should submit as well.
    modal.addEventListener(
      'keydown',
      function (e) {
        try {
          if (!e || e.key !== 'Enter') return;
          var t = e.target;
          if (!t || !(t.matches && t.matches('input#challenge-input, input[name="answer"], input[name="submission"], textarea[name="submission"], textarea[name="answer"]'))) {
            return;
          }
          void handleAttempt(modal, e);
        } catch (err) {}
      },
      true
    );
  }

  try {
    if (typeof window.getSolves !== 'function') {
      var getSolvesShim = function (challengeId) {
        var modal = document.getElementById('challenge-window') || document.querySelector('#challenge-window') || document;
        return loadSolvesReliable(modal, challengeId);
      };
      getSolvesShim.__ctfdModulesShim = true;
      window.getSolves = getSolvesShim;
    }
  } catch (_) {}

  try {
    document.addEventListener('click', function (e) {
      try {
        var t = e && e.target ? e.target : null;
        if (!t || !t.closest) return;
        var btn = t.closest('button.challenge-button');
        if (!btn) return;
        var modal = document.getElementById('challenge-window') || document.querySelector('#challenge-window');
        if (!modal) return;
        clearSolvesLoadState(modal);
        if (modal.dataset) {
          var key = currentChallengeKey(modal);
          if (key) modal.dataset.ctfdModulesCurrentChallengeKey = key;
        }
      } catch (_) {}
    }, true);
  } catch (_) {}

  document.addEventListener('DOMContentLoaded', attach);
})();
