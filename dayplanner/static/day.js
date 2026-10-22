// Review prompts (plan section 5): after every slot, at end of day, or off.
(function () {
  var review = document.getElementById("review");
  var banner = document.getElementById("review-banner");
  if (!review || !banner) return;

  var mode = review.dataset.mode;
  var isToday = review.dataset.today === "1";
  var isPast = review.dataset.past === "1";
  if (mode === "off" || !(isToday || isPast)) return;

  var loadedAt = Date.now();
  var nowAtLoad = parseInt(review.dataset.now, 10);
  var workEnd = parseInt(review.dataset.workEnd, 10);
  var rows = Array.prototype.slice.call(review.querySelectorAll("tr[data-start]"));

  function nowMinute() {
    if (!isToday) return Infinity;
    return nowAtLoad + Math.floor((Date.now() - loadedAt) / 60000);
  }

  function unreviewedBefore(now) {
    return rows.filter(function (r) {
      return r.dataset.reviewed === "0" && parseInt(r.dataset.end, 10) <= now;
    });
  }

  function show(text, row) {
    banner.textContent = "";
    banner.appendChild(document.createTextNode(text + " "));
    var a = document.createElement("a");
    a.href = "#" + row.id;
    a.textContent = "Review now";
    a.addEventListener("click", function () {
      row.classList.add("highlight");
      var input = row.querySelector("input[name=note]");
      if (input) setTimeout(function () { input.focus(); }, 300);
    });
    banner.appendChild(a);
    banner.hidden = false;
  }

  function update() {
    var now = nowMinute();
    var pending = unreviewedBefore(now);
    banner.hidden = true;
    if (!pending.length) return;
    if (mode === "slot" && now < workEnd) {
      var last = pending[pending.length - 1];
      show("How did " + last.dataset.label + " go?", last);
    } else if (now >= workEnd) {
      var n = pending.length;
      show("Your working day is over. " + n + (n === 1 ? " slot" : " slots") +
           " still to review.", pending[0]);
    }
  }

  update();
  if (isToday) setInterval(update, 30000);
})();
