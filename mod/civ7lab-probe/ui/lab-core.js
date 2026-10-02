// civ7lab: the probe runtime. Installs globalThis.C7Lab and nothing else.
//
// No imports, no engine calls at load time, no UI. An import that does not
// resolve stops the whole script, and a throw during startup can break a
// panel, so every failure here is printed rather than thrown.
//
// One collector answers two ways:
//
//   * `C7Lab.collect("tile", {x:20,y:7})` returns the object, which is what
//     `civ7lab live` calls over the inspector;
//   * `C7Lab.dump("tile", {x:20,y:7})` also prints it to UI.log as a record.
//
// Collectors are registered by name, so another script can add its own with
// C7Lab.register. See docs/probe.md.

(function installCiv7Lab() {
  "use strict";

  // Build stamp: a hash of the probe's files. After an edit,
  // tests/test_probe.py fails and prints the new line to paste here. It is
  // printed at load, and `civ7lab logs stamps` reads it back.
  var BUILD = "probe-53aea152";
  var PROTOCOL = 1;

  // UI.log cuts long lines. Records longer than this are split into numbered
  // fragments, each stating its length, so the reader can report a cut one.
  var CHUNK = 400;

  // Loaded again, as `civ7lab live` does after an edit: keep the registered
  // collectors and the record count. A hook installed by the earlier load
  // then sees the new collectors too.
  var previous = globalThis.C7Lab;
  var state = previous && previous.state ? previous.state : {
    sequence: 0,
    collectors: {},
    run: "r" + Date.now().toString(36)
  };
  var collectors = state.collectors;
  var runId = state.run;

  // Only console.error reaches UI.log. Both reach the inspector.
  function write(text) {
    try {
      console.error(text);
    } catch (error) {
      /* if printing itself fails there is nothing useful left to do */
    }
  }

  function log(text) {
    write("[C7LAB] " + JSON.stringify({
      v: PROTOCOL, seq: ++state.sequence, kind: "log", run: runId, data: String(text)
    }));
  }

  // Emit a record. Short ones go as a single line; long ones as fragments that
  // the reader reassembles and checks.
  function emit(kind, data, meta) {
    var record = { v: PROTOCOL, seq: ++state.sequence, kind: String(kind), run: runId };
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
      // A cycle or a live engine object in the data. Name the kind.
      write("[C7LAB] " + JSON.stringify({
        v: PROTOCOL, seq: state.sequence, kind: "error", run: runId,
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

  // Run an engine call and return any error as data, so the rest of a
  // collector's result still arrives.
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

  // Every property and method of an engine object. Walks the prototype chain,
  // since engine methods are not own properties.
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
    plan: previous ? previous.plan : undefined,
    state: state
  };

  // Read back by `civ7lab logs stamps`.
  write("[C7LAB] civ7lab:build probe " + BUILD);
  log("probe runtime installed, run " + runId);
})();
