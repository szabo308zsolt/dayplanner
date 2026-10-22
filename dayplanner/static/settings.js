(function () {
  var tz = document.getElementById("timezone");
  if (tz && tz.dataset.detect === "1") {
    try { tz.value = Intl.DateTimeFormat().resolvedOptions().timeZone || tz.value; } catch (e) {}
  }

  var add = document.getElementById("add-break");
  if (add) {
    add.addEventListener("click", function () {
      var rows = document.querySelectorAll("#breaks .break-row");
      var copy = rows[rows.length - 1].cloneNode(true);
      copy.querySelectorAll("input").forEach(function (i) { i.value = ""; });
      document.getElementById("breaks").appendChild(copy);
    });
  }
})();
