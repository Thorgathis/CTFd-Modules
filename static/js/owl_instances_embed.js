(function () {
  "use strict";

  if ((window.location.pathname || "").indexOf("/modules") === -1) return;

  function cleanupModal() {
    var modal = document.getElementById("owl-instances-modal");
    if (modal && modal.classList.contains("show") && modal.style.display !== "none") return;
    document.querySelectorAll(".modal-backdrop, #owl-instances-modal-backdrop").forEach(function (el) {
      el.remove();
    });
    document.body.classList.remove("modal-open");
    document.body.style.removeProperty("padding-right");
    document.body.style.removeProperty("overflow");
  }

  document.addEventListener("click", function (event) {
    var closeBtn =
      event.target &&
      event.target.closest &&
      event.target.closest(
        '#owl-instances-modal [data-dismiss="modal"], #owl-instances-modal [data-bs-dismiss="modal"], #owl-instances-modal .btn-close, #owl-instances-modal .close'
      );
    if (closeBtn) window.setTimeout(cleanupModal, 150);
  });

  document.addEventListener("hidden.bs.modal", function (event) {
    if (event.target && event.target.id === "owl-instances-modal") cleanupModal();
  });

  if (typeof window.owlEnsureInstancesMenu === "function") {
    window.owlEnsureInstancesMenu();
    return;
  }

  if (window.__ctfdModulesOwlBooted) return;
  window.__ctfdModulesOwlBooted = true;

  fetch("/plugins/ctfd-owl/assets/js/instances.js", { credentials: "same-origin" })
    .then(function (res) {
      return res.ok ? res.text() : null;
    })
    .then(function (source) {
      if (!source) return;
      source = source.replace(
        /return\s+p\.includes\((["'])\/challenges\1\);/,
        'return p.includes("/challenges") || p.includes("/modules");'
      );
      var script = document.createElement("script");
      script.id = "ctfd-modules-owl-instances-loader";
      script.textContent = source;
      document.body.appendChild(script);
      window.setTimeout(function () {
        if (typeof window.owlEnsureInstancesMenu === "function") window.owlEnsureInstancesMenu();
      }, 0);
    })
    .catch(function () {});
})();
