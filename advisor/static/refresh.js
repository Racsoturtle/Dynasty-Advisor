// The Refresh button's full rebuild. Loads Python in the browser (Pyodide),
// pulls fresh rosters, picks and scores from Sleeper, and reruns the same
// analysis the morning build ran on this morning's values and projections.
// This morning's trade offers are kept rather than searched again, minus any
// whose rosters changed. Returns {filename: text} for every page and data file.
window.FullRefresh = async function (status) {
  const base = new URL("engine/", location.href).href;
  const API = "https://api.sleeper.app/v1";
  const get = (url) => fetch(url).then((r) => { if (!r.ok) throw new Error(url + " " + r.status); return r; });
  const sleeper = (p) => get(API + p).then((r) => r.json());

  status("Loading this morning's data…");
  const raw = await get(base + "raw.json").then((r) => r.json());
  const LEAGUE = raw.sleeper.league.league_id;
  const s = raw.sleeper;

  status("Checking Sleeper…");
  const [league, state, rosters, users, tradedPicks] = await Promise.all([
    sleeper("/league/" + LEAGUE), sleeper("/state/nfl"), sleeper("/league/" + LEAGUE + "/rosters"),
    sleeper("/league/" + LEAGUE + "/users"), sleeper("/league/" + LEAGUE + "/traded_picks")]);
  const lastWeek = Number((league.settings || {}).playoff_week_start || 15) - 1;
  const weeks = Array.from({ length: lastWeek }, (_, i) => i + 1);
  const matchups = await Promise.all(weeks.map((w) => sleeper("/league/" + LEAGUE + "/matchups/" + w)));
  const fetchedAt = new Date();

  raw.baseline = { rosters: s.rosters, traded_picks: s.traded_picks };
  raw.morning_fetched_at = raw.fetched_at;
  raw.fetched_at = fetchedAt.toISOString();
  raw.sleeper = { ...s, league, state, rosters, users, traded_picks: tradedPicks,
                  matchups: Object.fromEntries(weeks.map((w, i) => [w, matchups[i]])) };
  // Players picked up since the morning that the trimmed player list left out.
  const missing = rosters.flatMap((r) => r.players || []).filter((pid) => !s.players[pid]);
  if (missing.length) {
    status("Looking up " + missing.length + " new player" + (missing.length === 1 ? "" : "s") + "…");
    const all = await sleeper("/players/nfl");
    missing.forEach((pid) => {
      const p = all[pid];
      if (p) s.players[pid] = Object.fromEntries(["full_name", "first_name", "last_name", "position", "team", "age",
        "injury_status"].filter((k) => p[k] != null).map((k) => [k, p[k]]));
    });
  }

  status("Starting the analysis engine…");
  if (!window.loadPyodide) {
    await new Promise((ok, fail) => {
      const tag = document.createElement("script");
      tag.src = base + "pyodide/pyodide.js";
      tag.onload = ok; tag.onerror = () => fail(new Error("couldn't load pyodide.js"));
      document.head.appendChild(tag);
    });
  }
  const [py, lib, app] = await Promise.all([
    loadPyodide({ indexURL: base + "pyodide/" }),
    get(base + "lib.zip").then((r) => r.arrayBuffer()),
    get(base + "app.zip").then((r) => r.arrayBuffer())]);
  py.unpackArchive(lib, "zip", { extractDir: "/lib" });
  py.unpackArchive(app, "zip", { extractDir: "/app" });

  status("Rebuilding every page…");
  await new Promise((ok) => setTimeout(ok, 30)); // let the status paint before Python takes over
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(fetchedAt);
  py.globals.set("RAW_JSON", JSON.stringify(raw));
  py.globals.set("TODAY", today);
  const files = py.runPython(`
import json, os, sys
sys.path[:0] = ["/app", "/lib"]
from datetime import date
from advisor import main, render
report = main.analyze(json.loads(RAW_JSON), today=date.fromisoformat(TODAY))
render.write_site(report, "/site")
json.dumps({n: open("/site/" + n).read() for n in os.listdir("/site") if n.endswith((".html", ".json"))})
`);
  return { at: fetchedAt.getTime(), files: JSON.parse(files) };
};
