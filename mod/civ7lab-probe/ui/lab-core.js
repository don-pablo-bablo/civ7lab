// civ7lab: the probe runtime. Installs globalThis.C7Lab and nothing else.
//
// This file is the only part of the toolkit that runs inside the game, and it
// is deliberately dull: no imports, no engine calls at load time, no UI. An
// import that does not resolve takes the whole script down, and a script that
// throws while the game is starting takes a panel down with it, so everything
// here is guarded and the failure mode is a printed line, never an exception.
//
// It exists so a question about the game can be asked two ways from one answer:
//
//   * over the UI remote debugger, where `C7Lab.collect("tile", {x:20,y:7})`
//     returns the object and `civ7lab live` prints it, with no reload or log;
//   * through the log, where `C7Lab.dump("tile", {x:20,y:7})` prints the same
//     object as records that survive the game exiting.
//
// Collectors are registered by name rather than exported, so the debugger can
// list what is available without knowing anything about this file, and so a
// project can add its own collectors in its own script without editing this one.

(function installCiv7Lab() {
  "use strict";

  // BUILD STAMP. Bump it when editing any probe script. Mod files are read at
  // game start, so an edit is inert until the game restarts or `civ7lab ui`
  // patches it. A check run against a stale build looks exactly like a check
  // run against a fresh one. Printing the stamp means the log states
  // which build actually ran instead of it being inferred from file times.
  var BUILD = "probe-2 21 Sep";
  var PROTOCOL = 1;

  // Long lines are truncated in UI.log and a truncated JSON object is a silent
  // loss, so records longer than this are split into numbered fragments, each
  // declaring its own length. The reader checks that length and reports a cut
  // fragment as an error instead of parsing half a measurement.
  var CHUNK = 400;

  if (globalThis.C7Lab && globalThis.C7Lab.build === BUILD) {
    return; // already installed by an earlier load of this same build
  }

  var sequence = 0;
  var collectors = {};
  var runId = "r" + Date.now().toString(36);

  // console.error, not console.log: only error reaches UI.log. Both reach the
  // remote debugger, so this one call serves both routes.
  function write(text) {
    try {
      console.error(text);
    } catch (error) {
      /* if printing itself fails there is nothing useful left to do */
    }
  }

  function log(text) {
    write("[C7LAB] " + JSON.stringify({
      v: PROTOCOL, seq: ++sequence, kind: "log", run: runId, data: String(text)
    }));
  }

  // Emit a record. Short ones go as a single line; long ones as fragments that
  // the reader reassembles and checks.
  function emit(kind, data, meta) {
    var record = { v: PROTOCOL, seq: ++sequence, kind: String(kind), run: runId };
    try {
      record.turn = Game.turn;
    } catch (error) { /* no game in progress; the record is still valid */ }
    if (meta) {
      for (var key in meta) {
        if (Object.prototype.hasOwnProperty.call(meta, key)) record[key] = meta[key];
      }
    }
    record.data = data;

    var text;
    try {
      text = JSON.stringify(record);
    } catch (error) {
      // A cycle or a live engine object got into the payload. Say so with the
      // kind attached, because "which collector" is the whole question.
      write("[C7LAB] " + JSON.stringify({
        v: PROTOCOL, seq: sequence, kind: "error", run: runId,
        data: "record " + kind + " will not serialise: " + String(error)
      }));
      return null;
    }

    if (text.length <= CHUNK) {
      write("[C7LAB] " + text);
      return record;
    }
    var id = runId + "-" + record.seq;
    var total = Math.ceil(text.length / CHUNK);
    for (var index = 0; index < total; index++) {
      var part = text.substr(index * CHUNK, CHUNK);
      write("[C7LAB#] " + JSON.stringify({
        id: id, i: index, n: total, len: part.length, s: part
      }));
    }
    return record;
  }

  // Run something that touches the engine and never let it escape. The failure
  // is returned as data, so a collector that half worked still reports the half
  // that did rather than vanishing.
  function safe(what, fallback) {
    try {
      return what();
    } catch (error) {
      return { error: String(error && error.message ? error.message : error),
               fallback: fallback === undefined ? null : fallback };
    }
  }

  function register(name, fn, description) {
    collectors[name] = { fn: fn, description: description || "" };
    return name;
  }

  function collect(name, args) {
    var entry = collectors[name];
    if (!entry) {
      return { error: "no collector named " + name,
               available: Object.keys(collectors) };
    }
    try {
      return entry.fn(args || {});
    } catch (error) {
      return { error: String(error && error.stack ? error.stack : error),
               collector: name, args: args || {} };
    }
  }

  function dump(name, args) {
    var data = collect(name, args);
    emit(name, data, { args: args || {} });
    return data;
  }

  // Answer "what does this engine object actually have on it", which is a
  // question this project has had to answer by hand more than once. Walks the
  // prototype chain, because the interesting members are never own properties.
  function members(target) {
    var object = target;
    if (typeof target === "string") {
      try {
        object = (0, eval)(target);
      } catch (error) {
        return { error: "cannot resolve " + target + ": " + String(error) };
      }
    }
    if (object === null || object === undefined) return { error: "null or undefined" };
    var names = [];
    var walker = object;
    var guard = 0;
    while (walker && guard++ < 10) {
      var own = Object.getOwnPropertyNames(walker);
      for (var i = 0; i < own.length; i++) {
        if (names.indexOf(own[i]) < 0 && own[i] !== "constructor") names.push(own[i]);
      }
      walker = Object.getPrototypeOf(walker);
    }
    var described = [];
    for (var j = 0; j < names.length; j++) {
      var name = names[j];
      var kind = "?";
      try {
        var value = object[name];
        kind = typeof value;
        if (kind === "function") kind = "function/" + value.length;
        else if (value && kind === "object") kind = Array.isArray(value) ? "array/" + value.length : "object";
        else if (kind !== "function") kind = kind + " = " + JSON.stringify(value);
      } catch (error) {
        kind = "threw on read";
      }
      described.push(name + ": " + kind);
    }
    return { of: typeof target === "string" ? target : "(object)", members: described.sort() };
  }

  globalThis.C7Lab = {
    build: BUILD,
    protocol: PROTOCOL,
    run: runId,
    log: log,
    emit: emit,
    safe: safe,
    register: register,
    collect: collect,
    dump: dump,
    members: members,
    list: function () {
      var out = {};
      for (var name in collectors) {
        if (Object.prototype.hasOwnProperty.call(collectors, name)) {
          out[name] = collectors[name].description;
        }
      }
      return out;
    },
    // Settings the host can change over the debugger without a reload, which is
    // the point: an unattended run turns on per-turn dumping, an interactive
    // session leaves it off so the log stays readable.
    config: { dumpOnTurn: false, dumpOnCitySelect: false, tilesPerTurn: 0 }
  };

  // The line every session should start with. `civ7lab logs stamps` reads it
  // back, so a report can state the build that ran rather than assuming.
  write("[C7LAB] civ7lab:build probe " + BUILD);
  log("probe runtime installed, run " + runId);
})();
