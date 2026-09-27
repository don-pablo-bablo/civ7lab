// civ7lab: when the probe fires by itself.
//
// Interactive work does not need this file: `civ7lab live collect ...` asks a
// question at the moment it is asked. Unattended work does. A run that plays
// forty turns with nobody watching has to decide in advance what to record,
// because there is no one there to hover a tile, and the only trace it leaves
// is the log.
//
// So a run carries a plan, a list of collectors with the turns they fire on,
// and this file executes it. `civ7lab run` writes the plan into
// ui/lab-plan.js before launching, which is how a measurement is specified
// once and repeated exactly.

(function installHooks() {
  "use strict";
  if (!globalThis.C7Lab) {
    console.error("[C7LAB] hooks loaded before the runtime; check the modinfo order");
    return;
  }
  var Lab = globalThis.C7Lab;

  // A plan entry: { collector, args, every, from, to }. `every` is a turn
  // interval, so a long run can sample rather than record every turn of
  // everything and drown the log it depends on.
  function shouldFire(entry, turn) {
    if (entry.from !== undefined && turn < entry.from) return false;
    if (entry.to !== undefined && turn > entry.to) return false;
    var every = entry.every || 1;
    var base = entry.from === undefined ? 0 : entry.from;
    return ((turn - base) % every) === 0;
  }

  function runPlan(when, turn) {
    var plan = Lab.plan && Lab.plan[when];
    if (!plan || !plan.length) return;
    for (var i = 0; i < plan.length; i++) {
      var entry = plan[i];
      if (when === "onTurn" && !shouldFire(entry, turn)) continue;
      try {
        Lab.dump(entry.collector, entry.args || {});
      } catch (error) {
        Lab.log("plan entry " + entry.collector + " threw: " + String(error));
      }
    }
  }

  engine.on("TurnBegin", function (data) {
    try {
      var turn = data && data.turn !== undefined ? data.turn : Game.turn;
      if (Lab.config.dumpOnTurn) Lab.dump("game", {});
      runPlan("onTurn", turn);
    } catch (error) {
      Lab.log("TurnBegin handler threw: " + String(error));
    }
  });

  // The age transition is the one moment this project most often needs both
  // sides of, and it is the one moment that cannot be re-run without replaying
  // an age. Record it unconditionally: a few records are cheap, and a missed
  // transition costs a playthrough.
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
      if (Lab.config.dumpOnCitySelect) {
        var city = Cities.get(event.cityID);
        Lab.dump("city", { name: city ? Locale.compose(city.name) : undefined });
      }
      runPlan("onCitySelect", Game.turn);
    } catch (error) {
      Lab.log("CitySelectionChanged handler threw: " + String(error));
    }
  });

  Lab.log("hooks installed; plan entries: " +
    (Lab.plan ? Object.keys(Lab.plan).map(function (key) {
      return key + "=" + (Lab.plan[key] || []).length;
    }).join(" ") : "none"));
})();
