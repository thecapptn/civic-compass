/* Progressive enhancement only.
   Every page is complete and usable with this file blocked. Nothing here fetches data, changes a
   fact, or gates an instruction. If it fails, the site still works. */

(function () {
  "use strict";

  /* Copy address buttons. Added by script because a copy button is meaningless without
     scripting — the address itself is already selectable text in the markup. */
  document.querySelectorAll(".loc__addrtext").forEach(function (span) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "copybtn";
    btn.textContent = "Copy address";
    var live = document.createElement("span");
    live.setAttribute("role", "status");
    live.className = "sr-only";
    live.style.cssText = "position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)";

    btn.addEventListener("click", function () {
      var text = span.textContent.trim();
      var done = function () {
        btn.textContent = "Copied";
        live.textContent = "Address copied to the clipboard.";
        window.setTimeout(function () { btn.textContent = "Copy address"; }, 4000);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () {
          live.textContent = "Could not copy. Select the address and copy it manually.";
        });
      } else {
        live.textContent = "Copying is not available in this browser. Select the address and copy "
          + "it manually.";
      }
    });
    span.parentNode.appendChild(btn);
    span.parentNode.appendChild(live);
  });

  /* Checklist ticks, stored on this device only.
     Keyed by election so two plans do not collide. No jurisdiction, address, or identifier that
     could describe the person is written. */
  var list = document.querySelector("[data-checklist]");
  if (list && window.localStorage) {
    var key = "cc.checklist." + list.getAttribute("data-checklist");
    var state = {};
    try { state = JSON.parse(window.localStorage.getItem(key) || "{}"); } catch (e) { state = {}; }

    list.querySelectorAll("[data-check]").forEach(function (box) {
      var id = box.getAttribute("data-check");
      if (state[id]) { box.checked = true; }
      box.addEventListener("change", function () {
        state[id] = box.checked;
        try { window.localStorage.setItem(key, JSON.stringify(state)); } catch (e) { /* full or
          blocked: ticking still works for this visit, which is the important part */ }
      });
    });

    var clear = document.createElement("button");
    clear.type = "button";
    clear.className = "btn btn--quiet";
    clear.textContent = "Clear ticks on this device";
    clear.addEventListener("click", function () {
      try { window.localStorage.removeItem(key); } catch (e) { /* nothing to clear */ }
      list.querySelectorAll("[data-check]").forEach(function (b) { b.checked = false; });
    });
    list.parentNode.insertBefore(clear, list.nextSibling);
  }
})();
