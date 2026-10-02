// civ7lab: runs the recording plan during unattended runs.
//
// A plan lists collectors and the turns they fire on. `civ7lab run --plan`
// writes it into ui/lab-plan.js before launch, and this file dumps each
// collector to UI.log when its turn comes. `civ7lab live` does not use it.

(function installHooks() {
  "use strict";
  if (!globalThis.C7Lab) {
    console.error("[C7LAB] hooks loaded before the runtime; check the modinfo order");
    return;
  }
  var Lab = globalThis.C7Lab;

  // A plan entry: { collector, args, every, from, to }. `every` is a turn
  // interval, so a long run can sample instead of filling the log.
  function shouldFire(entry, turn) {
    if (entry.from !== undefined && turn < entry.from) return false;
    if (entry.to !== undefined && turn > entry.to) return false;
    var every = entry.every || 1;
    var base = entry.from === undefined ? 0 : entry.from;
    return ((turn - base) % every) === 0;
  }

  // `defaults` fill in arguments an entry leaves out, such as the selected
  // city's name for onCitySelect.
  function runPlan(when, turn, defaults) {
    var plan = Lab.plan && Lab.plan[when];
    if (!plan || !plan.length) return;
    for (var i = 0; i < plan.length; i++) {
      var entry = plan[i];
      if (when === "onTurn" && !shouldFire(entry, turn)) continue;
      var args = {};
      var key;
      for (key in defaults || {}) args[key] = defaults[key];
      for (key in entry.args || {}) args[key] = entry.args[key];
      try {
        Lab.dump(entry.collector, args);
      } catch (error) {
        Lab.log("plan entry " + entry.collector + " threw: " + String(error));
      }
    }
  }

  engine.on("TurnBegin", function (data) {
    try {
      var turn = data && data.turn !== undefined ? data.turn : Game.turn;
      runPlan("onTurn", turn);
    } catch (error) {
      Lab.log("TurnBegin handler threw: " + String(error));
    }
  });

  // Always record the age transition. It cannot be repeated without playing
  // the whole age again.
  engine.on("GameAgeEnded", function () {
    try {
      Lab.dump("game", {});
      runPlan("onAgeEnd", Game.turn);
    } catch (error) {
      Lab.log("GameAgeEnded handler threw: " + String(error));
    }
  });

  engine.on("CitySelectionChanged", function (event) {
    try {
      if (!event || !event.selected || !event.cityID) return;
      if (event.cityID.owner !== GameContext.localPlayerID) return;
      var city = Cities.get(event.cityID);
      runPlan("onCitySelect", Game.turn,
              city ? { name: Locale.compose(city.name) } : {});
    } catch (error) {
      Lab.log("CitySelectionChanged handler threw: " + String(error));
    }
  });

  Lab.log("hooks installed; plan entries: " +
    (Lab.plan ? Object.keys(Lab.plan).map(function (key) {
      return key + "=" + (Lab.plan[key] || []).length;
    }).join(" ") : "none"));
})();
