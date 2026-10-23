(function () {
  "use strict";

  document.querySelectorAll("form").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      var button = form.querySelector("button[type=submit]");
      if (!button) return;
      if (button.dataset.busy === "1") {
        event.preventDefault();
        return;
      }
      button.dataset.busy = "1";
      button.disabled = true;
      button.textContent = "处理中…";
    });
  });

  document.querySelectorAll('a[href^="http"]').forEach(function (link) {
    link.setAttribute("rel", "noopener noreferrer");
  });
})();
