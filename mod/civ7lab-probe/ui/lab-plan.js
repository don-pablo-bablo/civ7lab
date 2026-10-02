// civ7lab: the recording plan for one run. GENERATED: `civ7lab run --plan`
// overwrites this file. Without a plan it is empty.
//
// Shape:
//   C7Lab.plan = {
//     onTurn:       [{ collector: "city", args: {}, every: 5, from: 10, to: 44 }],
//     onCitySelect: [{ collector: "yieldtree", args: { yield: "YIELD_SCIENCE" } }],
//     onAgeEnd:     [{ collector: "city", args: { all: true } }]
//   };
// onCitySelect entries get the selected city's name unless args give one.
(function () {
  "use strict";
  if (!globalThis.C7Lab) return;
  globalThis.C7Lab.plan = { onTurn: [], onCitySelect: [], onAgeEnd: [] };
})();
