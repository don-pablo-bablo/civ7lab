// civ7lab: the recording plan for one run. GENERATED: `civ7lab run --plan`
// overwrites this file, and an interactive session leaves it empty.
//
// Shape:
//   C7Lab.plan = {
//     onTurn:       [{ collector: "city", args: {}, every: 5, from: 10, to: 44 }],
//     onCitySelect: [{ collector: "yieldtree", args: { yield: "YIELD_SCIENCE" } }],
//     onAgeEnd:     [{ collector: "city", args: { all: true } }]
//   };
//
// Kept as a file rather than a setting because a plan has to be in place before
// the first turn of an unattended run, and there is nobody there to type it.
(function () {
  "use strict";
  if (!globalThis.C7Lab) return;
  globalThis.C7Lab.plan = { onTurn: [], onCitySelect: [], onAgeEnd: [] };
  globalThis.C7Lab.config.dumpOnCitySelect = true;
})();
