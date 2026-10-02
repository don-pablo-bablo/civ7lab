// civ7lab: the collectors. Each returns plain data, with no engine objects and
// no cycles, so the same value can go into UI.log or back over the inspector.
//
// Every engine call is one the shipped UI makes: GameplayMap.getYields returns
// [yieldHash, amount] pairs (lenses/layer/yields-layer.ts:162),
// MapConstructibles.getConstructibles(x, y) returns component ids
// (tooltips/plot-tooltip/helpers.ts:418), and city.Yields.getYieldsForNode is
// what City Details walks (city-details/model-city-details.ts:271).

(function registerCollectors() {
  "use strict";
  if (!globalThis.C7Lab) {
    console.error("[C7LAB] collectors loaded before the runtime; check the modinfo order");
    return;
  }
  var Lab = globalThis.C7Lab;
  var safe = Lab.safe;

  // ---------------------------------------------------------------- helpers

  function yieldName(hash) {
    try {
      var definition = GameInfo.Yields.lookup(hash);
      return definition ? definition.YieldType : String(hash);
    } catch (error) {
      return String(hash);
    }
  }

  function text(value) {
    try {
      return value ? Locale.compose(value) : "";
    } catch (error) {
      return String(value || "");
    }
  }

  function yieldsAt(x, y, playerId) {
    var out = {};
    try {
      var index = GameplayMap.getIndexFromXY(x, y);
      var pairs = GameplayMap.getYields(index, playerId);
      if (!pairs) return out;
      for (var i = 0; i < pairs.length; i++) {
        out[yieldName(pairs[i][0])] = pairs[i][1];
      }
    } catch (error) {
      out.error = String(error);
    }
    return out;
  }

  function constructiblesAt(x, y) {
    var listed = [];
    try {
      var ids = MapConstructibles.getConstructibles(x, y) || [];
      for (var i = 0; i < ids.length; i++) {
        listed.push(safe(function () {
          var instance = Constructibles.getByComponentID(ids[i]);
          if (!instance) return { id: ids[i] && ids[i].id, missing: true };
          var definition = GameInfo.Constructibles.lookup(instance.type);
          return {
            type: definition ? definition.ConstructibleType : instance.type,
            name: definition ? text(definition.Name) : "",
            class: definition ? definition.ConstructibleClass : "",
            age: definition ? definition.Age : null,
            complete: instance.complete,
            damaged: instance.damaged,
            owner: instance.owner,
            id: ids[i] && ids[i].id
          };
        }));
      }
    } catch (error) {
      listed.push({ error: String(error) });
    }
    return listed;
  }

  function localPlayer() {
    try {
      return GameContext.localPlayerID;
    } catch (error) {
      return -1;
    }
  }

  // ------------------------------------------------------------- collectors

  Lab.register("game", function () {
    return {
      turn: safe(function () { return Game.turn; }),
      age: safe(function () { return GameInfo.Ages.lookup(Game.age).AgeType; }),
      maxTurns: safe(function () { return Game.maxTurns; }),
      localPlayer: localPlayer(),
      mapWidth: safe(function () { return GameplayMap.getGridWidth(); }),
      mapHeight: safe(function () { return GameplayMap.getGridHeight(); }),
      players: safe(function () {
        var out = [];
        var ids = Players.getAliveIds();
        for (var i = 0; i < ids.length; i++) {
          var player = Players.get(ids[i]);
          if (!player) continue;
          out.push({
            id: ids[i],
            civ: player.civilizationFullName ? text(player.civilizationFullName) : "",
            isHuman: Players.isHuman(ids[i]),
            isMajor: player.isMajor,
            cities: safe(function () { return player.Cities ? player.Cities.getCityIds().length : 0; })
          });
        }
        return out;
      })
    };
  }, "turn, age, map size and who is playing");

  Lab.register("tile", function (args) {
    var x = args.x, y = args.y;
    var player = args.player === undefined ? localPlayer() : args.player;
    if (x === undefined || y === undefined) return { error: "tile needs {x, y}" };
    return {
      x: x, y: y,
      yields: yieldsAt(x, y, player),
      terrain: safe(function () { return GameInfo.Terrains.lookup(GameplayMap.getTerrainType(x, y)).TerrainType; }),
      biome: safe(function () { return GameInfo.Biomes.lookup(GameplayMap.getBiomeType(x, y)).BiomeType; }),
      feature: safe(function () {
        var type = GameplayMap.getFeatureType(x, y);
        var definition = type === undefined || type === null ? null : GameInfo.Features.lookup(type);
        return definition ? definition.FeatureType : null;
      }),
      resource: safe(function () {
        var type = GameplayMap.getResourceType(x, y);
        var definition = type === undefined || type === null ? null : GameInfo.Resources.lookup(type);
        return definition ? definition.ResourceType : null;
      }),
      owner: safe(function () { return GameplayMap.getOwner(x, y); }),
      district: safe(function () {
        var id = MapCities.getDistrict(x, y);
        if (!id) return null;
        var district = Districts.get(id);
        if (!district) return null;
        var definition = GameInfo.Districts.lookup(district.type);
        return definition ? definition.DistrictType : String(district.type);
      }),
      city: safe(function () {
        // getOwningCityFromXY returns a ComponentID, {owner, id, type}, not
        // a city, so .name on it is empty rather than an error. Measured
        // live, 21 Sep 2026.
        var componentId = GameplayMap.getOwningCityFromXY(x, y);
        if (!componentId) return null;
        var city = Cities.get(componentId);
        return city ? text(city.name) : null;
      }),
      constructibles: constructiblesAt(x, y)
    };
  }, "one tile: yields, terrain, district, and what stands on it");

  Lab.register("tiles", function (args) {
    // Either a radius around a point, or a rectangle.
    var out = [];
    var player = args.player === undefined ? localPlayer() : args.player;
    var points = [];
    if (args.radius !== undefined && args.x !== undefined) {
      var indices = safe(function () {
        return GameplayMap.getPlotIndicesInRadius(args.x, args.y, args.radius);
      }, []);
      if (indices && indices.length) {
        for (var i = 0; i < indices.length; i++) {
          var location = GameplayMap.getLocationFromIndex(indices[i]);
          points.push([location.x, location.y]);
        }
      }
    } else if (args.rect) {
      for (var x = args.rect[0]; x <= args.rect[2]; x++) {
        for (var y = args.rect[1]; y <= args.rect[3]; y++) points.push([x, y]);
      }
    } else {
      return { error: "tiles needs {x, y, radius} or {rect:[x0,y0,x1,y1]}" };
    }
    var collector = Lab.collect;
    for (var p = 0; p < points.length; p++) {
      var tile = collector("tile", { x: points[p][0], y: points[p][1], player: player });
      // Skip empty tiles unless args.all: they are most of the map.
      var interesting = args.all || (tile.constructibles && tile.constructibles.length) ||
        (tile.yields && Object.keys(tile.yields).length);
      if (interesting) out.push(tile);
    }
    return { count: out.length, tiles: out };
  }, "many tiles at once: {x,y,radius} or {rect:[x0,y0,x1,y1]}");

  function cityIds(args) {
    var ids = [];
    try {
      var owner = args && args.player !== undefined ? args.player : localPlayer();
      var player = Players.get(owner);
      if (!player || !player.Cities) return ids;
      var all = player.Cities.getCityIds();
      for (var i = 0; i < all.length; i++) {
        var city = Cities.get(all[i]);
        if (!city) continue;
        if (args && args.name && text(city.name).toLowerCase().indexOf(String(args.name).toLowerCase()) < 0) continue;
        ids.push(all[i]);
      }
    } catch (error) { /* an empty list reads the same as no cities */ }
    return ids;
  }

  Lab.register("cities", function (args) {
    var ids = cityIds(args || {});
    var out = [];
    for (var i = 0; i < ids.length; i++) {
      out.push(safe(function () {
        var city = Cities.get(ids[i]);
        return {
          name: text(city.name),
          x: city.location.x, y: city.location.y,
          population: city.population,
          isCapital: city.isCapital,
          id: ids[i].id
        };
      }));
    }
    return out;
  }, "every city of a player, briefly");

  Lab.register("city", function (args) {
    var ids = cityIds(args || {});
    if (!ids.length) return { error: "no city matched", args: args || {} };
    var results = [];
    for (var i = 0; i < ids.length; i++) {
      results.push(cityDetail(ids[i], args || {}));
    }
    return results.length === 1 ? results[0] : results;
  }, "one city in full: yields, buildings per tile, Great Works payouts");

  function cityDetail(cityId, args) {
    var city = Cities.get(cityId);
    if (!city) return { error: "no city for id" };
    var detail = {
      name: text(city.name),
      x: city.location.x, y: city.location.y,
      population: city.population,
      isCapital: city.isCapital,
      yields: safe(function () {
        // getNetYield takes a yield TYPE (city-banners.ts:603 passes
        // YieldTypes.YIELD_FOOD), while getYieldsForNode takes a yield INDEX
        // (model-city-details.ts:288). Mixing them up returns wrong numbers
        // rather than an error.
        var out = {};
        for (var i = 0; i < GameInfo.Yields.length; i++) {
          var definition = GameInfo.Yields[i];
          if (!definition) continue;
          out[definition.YieldType] = city.Yields.getNetYield(definition.$hash);
        }
        return out;
      }),
      greatWorks: greatWorks(city),
      tiles: []
    };
    // The city's tiles that have something on them, or all with args.all.
    detail.tiles = safe(function () {
      var out = [];
      var purchased = city.getPurchasedPlots ? city.getPurchasedPlots() : null;
      if (!purchased) return out;
      for (var i = 0; i < purchased.length; i++) {
        var location = GameplayMap.getLocationFromIndex(purchased[i]);
        var standing = constructiblesAt(location.x, location.y);
        if (!standing.length && !args.all) continue;
        out.push({
          x: location.x, y: location.y,
          district: safe(function () {
            var id = MapCities.getDistrict(location.x, location.y);
            var district = id ? Districts.get(id) : null;
            if (!district) return null;
            var definition = GameInfo.Districts.lookup(district.type);
            return definition ? definition.DistrictType : null;
          }),
          yields: yieldsAt(location.x, location.y, city.owner),
          constructibles: standing
        });
      }
      return out;
    }, []);
    if (args.tree) detail.tree = yieldTree(city, args);
    return detail;
  }

  // What each building's Great Works pay, per yield, straight from
  // city.Constructibles.
  function greatWorks(city) {
    return safe(function () {
      var store = city.Constructibles;
      if (!store || !store.getGreatWorkBuildings) return [];
      var buildings = store.getGreatWorkBuildings() || [];
      var out = [];
      for (var i = 0; i < buildings.length; i++) {
        var componentId = buildings[i].constructibleID;
        var instance = Constructibles.getByComponentID(componentId);
        var definition = instance ? GameInfo.Constructibles.lookup(instance.type) : null;
        var paying = {};
        for (var y = 0; y < GameInfo.Yields.length; y++) {
          var yieldDefinition = GameInfo.Yields[y];
          if (!yieldDefinition) continue;
          var amount = store.getBuildingYieldFromGreatWorks(yieldDefinition.YieldType, componentId);
          if (amount) paying[yieldDefinition.YieldType] = amount;
        }
        out.push({
          building: definition ? definition.ConstructibleType : String(componentId && componentId.id),
          slots: store.getNumGreatWorkSlots(componentId),
          paying: paying
        });
      }
      return out;
    }, []);
  }

  // The attribution tree, as data. A node is a TrackedValue in one of three
  // shapes: an attribute with .base (walk .base.steps when the base is an
  // ADDITION, otherwise .base itself; .modifier is a node of its own), an
  // addition with .steps, or a plain value.
  //
  // The engine gives totals it does not fully break down: a building node can
  // read 15 while its children sum to 12. The gap is reported as
  // `unexplained`.
  var MAX_DEPTH = 14;

  function isAddition(node) {
    try {
      if (typeof GameValueStepTypes !== "undefined" && node.type !== undefined) {
        return node.type === GameValueStepTypes.ADDITION;
      }
    } catch (error) { /* fall through to the shape test */ }
    return Array.isArray(node.steps) && node.steps.length > 0;
  }

  function contextOf(node) {
    return safe(function () {
      var context = node && node.context;
      if (!context) return null;
      if (typeof ComponentIDTypes !== "undefined" && context.type === ComponentIDTypes.PLOT) {
        var location = GameplayMap.getLocationFromIndex(context.id);
        return location ? { plot: [location.x, location.y] } : null;
      }
      var instance = Constructibles.getByComponentID ? Constructibles.getByComponentID(context) : null;
      if (!instance) return { id: context.id };
      var definition = GameInfo.Constructibles.lookup(instance.type);
      return { constructible: definition ? definition.ConstructibleType : instance.type };
    }, null);
  }

  function walk(node, depth) {
    if (!node || depth > MAX_DEPTH) return null;
    var value = typeof node.value === "number" ? node.value : 0;
    var entry = {
      label: node.description ? text(node.description) : "",
      value: value,
      from: contextOf(node),
      children: []
    };
    var sum = 0;
    try {
      if (node.base) {
        if (isAddition(node.base)) {
          var steps = Array.isArray(node.base.steps) ? node.base.steps : [];
          for (var i = 0; i < steps.length; i++) {
            var child = walk(steps[i], depth + 1);
            if (child) { entry.children.push(child); sum += child.value; }
          }
        } else {
          var baseChild = walk(node.base, depth + 1);
          if (baseChild) { entry.children.push(baseChild); sum += baseChild.value; }
        }
        if (node.modifier) {
          var modifier = walk(node.modifier, depth + 1);
          if (modifier) { modifier.isModifier = true; entry.children.push(modifier); }
        }
      } else if (Array.isArray(node.steps)) {
        for (var s = 0; s < node.steps.length; s++) {
          var step = walk(node.steps[s], depth + 1);
          if (step) { entry.children.push(step); sum += step.value; }
        }
      }
    } catch (error) {
      entry.error = String(error);
    }
    if (entry.children.length && !node.modifier && Math.abs(sum - value) > 0.01) {
      entry.unexplained = Number((value - sum).toFixed(2));
    }
    return entry;
  }

  function nodePaths() {
    if (typeof CityYieldNodes === "undefined") return null;
    return [
      ["INCOME/BUILDINGS", [CityYieldNodes.INCOME, CityYieldNodes.BUILDING_YIELDS]],
      ["INCOME/GREAT_WORKS", [CityYieldNodes.INCOME, CityYieldNodes.YIELD_FROM_GREAT_WORKS]],
      ["INCOME/IMPROVEMENTS", [CityYieldNodes.INCOME, CityYieldNodes.IMPROVEMENT_YIELDS]],
      ["INCOME/RESOURCES", [CityYieldNodes.INCOME, CityYieldNodes.YIELD_FROM_RESOURCES]],
      ["INCOME/CITY_EFFECTS", [CityYieldNodes.INCOME, CityYieldNodes.CITY_EFFECTS_YIELDS]],
      ["INCOME/TRADITIONS", [CityYieldNodes.INCOME, CityYieldNodes.ACTIVE_CIV_TRADITIONS]],
      ["DEDUCTIONS/BUILDING_MAINTENANCE", [CityYieldNodes.DEDUCTIONS, CityYieldNodes.BUILDING_MAINTENANCE]],
      ["DEDUCTIONS/WORKER_MAINTENANCE", [CityYieldNodes.DEDUCTIONS, CityYieldNodes.MAINTENANCE_FROM_WORKERS]]
    ];
  }

  function yieldTree(city, args) {
    var paths = nodePaths();
    if (!paths) return { error: "CityYieldNodes is not exposed to this script" };
    var store = city.Yields;
    if (!store) return { error: "city.Yields unavailable" };
    var wanted = args && args.yield ? String(args.yield) : null;
    var out = {};
    for (var i = 0; i < GameInfo.Yields.length; i++) {
      var definition = GameInfo.Yields[i];
      if (!definition) continue;
      if (wanted && definition.YieldType !== wanted) continue;
      var sections = {};
      for (var p = 0; p < paths.length; p++) {
        var label = paths[p][0];
        var node = safe(function () { return store.getYieldsForNode(i, paths[p][1], true); }, null);
        if (!node || node.error) continue;
        var walked = walk(node, 0);
        if (walked && (walked.value || walked.children.length)) sections[label] = walked;
      }
      if (Object.keys(sections).length) out[definition.YieldType] = sections;
    }
    return out;
  }

  Lab.register("yieldtree", function (args) {
    var ids = cityIds(args || {});
    if (!ids.length) return { error: "no city matched", args: args || {} };
    var city = Cities.get(ids[0]);
    return { city: text(city.name), tree: yieldTree(city, args || {}) };
  }, "a city's full yield attribution tree: {name, yield}");

  Lab.register("greatworks", function (args) {
    var ids = cityIds(args || {});
    var out = [];
    for (var i = 0; i < ids.length; i++) {
      var city = Cities.get(ids[i]);
      if (city) out.push({ city: text(city.name), buildings: greatWorks(city) });
    }
    return out;
  }, "Great Work slots and what they pay, per city");

  // Whether a mod's SQL reached the running game's database. No tags with the
  // mod's prefix means its rules never loaded, whatever else is wrong.
  Lab.register("tags", function (args) {
    var prefix = args && args.prefix ? String(args.prefix) : "";
    var type = args && args.type ? String(args.type) : "";
    var out = [];
    try {
      for (var i = 0; i < GameInfo.TypeTags.length; i++) {
        var row = GameInfo.TypeTags[i];
        if (!row) continue;
        if (prefix && String(row.Tag).indexOf(prefix) !== 0) continue;
        if (type && row.Type !== type) continue;
        out.push({ tag: row.Tag, type: row.Type });
      }
    } catch (error) {
      return { error: String(error) };
    }
    return { count: out.length, tags: out.slice(0, args && args.limit ? args.limit : 500) };
  }, "runtime TypeTags, to prove a mod's SQL reached the database: {prefix, type}");

  Lab.register("def", function (args) {
    // Any GameInfo row by type name, to confirm a definition edit in play.
    var table = args && args.table ? String(args.table) : "Constructibles";
    var type = args && args.type ? String(args.type) : "";
    return safe(function () {
      var rows = GameInfo[table];
      if (!rows) return { error: "no GameInfo table " + table };
      var found = rows.lookup ? rows.lookup(type) : null;
      if (!found) {
        for (var i = 0; i < rows.length; i++) {
          var row = rows[i];
          if (!row) continue;
          var identity = row[table.replace(/s$/, "") + "Type"] || row.Type;
          if (identity === type) { found = row; break; }
        }
      }
      if (!found) return { error: type + " not found in " + table };
      var plain = {};
      for (var key in found) {
        var value = found[key];
        if (value === null || ["string", "number", "boolean"].indexOf(typeof value) >= 0) plain[key] = value;
      }
      return plain;
    });
  }, "one GameInfo row: {table, type}");

  Lab.log("collectors ready: " + Object.keys(Lab.list()).join(", "));
})();
