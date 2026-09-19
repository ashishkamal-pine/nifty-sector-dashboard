"""
store.py
--------
A small cache in front of every expensive build, with two jobs:

  1. Never make a page wait for work that has already been done.
  2. Never make a page wait for work that could happen behind it.

STALE-WHILE-REVALIDATE

Each entry has a `fresh` window and a longer `max_stale` window:

    age < fresh          -> serve it, do nothing
    fresh < age < stale  -> serve it IMMEDIATELY, rebuild in the background
    age > max_stale      -> too old to show; build and wait
    no entry             -> build and wait

So a refresh inside the stale window is instant and the new data lands a moment
later, rather than the page freezing for five seconds while prices that barely
moved are fetched again.

SINGLE FLIGHT

Two requests for the same key at the same moment produce one build, not two.
The second waits on the first. Without this, opening two tabs, or an auto-refresh
landing on top of a manual one, would double the upstream traffic.

WARMING

`warm()` runs builders on a background thread at startup, so the first page load
usually finds everything already in the cache.
"""

import time
import threading


class Store:
    def __init__(self, workers=4):
        self._data = {}                       # key -> (built_at, value)
        self._lock = threading.Lock()
        self._building = {}                   # key -> Event, for single-flight
        self._sem = threading.Semaphore(workers)

    # ------------------------------------------------------------------
    def peek(self, key):
        with self._lock:
            hit = self._data.get(key)
        if not hit:
            return None, None
        return hit[1], time.time() - hit[0]

    def put(self, key, value):
        with self._lock:
            self._data[key] = (time.time(), value)

    def invalidate(self, prefix=None):
        with self._lock:
            if prefix is None:
                self._data.clear()
            else:
                for k in [k for k in self._data if str(k).startswith(prefix)]:
                    del self._data[k]

    def stats(self):
        with self._lock:
            now = time.time()
            return {str(k): round(now - v[0], 1) for k, v in self._data.items()}

    # ------------------------------------------------------------------
    def get(self, key, builder, fresh=45, max_stale=900, force=False):
        """
        -> (value, age_seconds, state)
        state: "fresh" | "stale" (served stale, refreshing behind) | "built"
        """
        if not force:
            value, age = self.peek(key)
            if value is not None:
                if age <= fresh:
                    return value, age, "fresh"
                if age <= max_stale:
                    self._refresh_async(key, builder)
                    return value, age, "stale"
        return self._build_blocking(key, builder), 0.0, "built"

    # ------------------------------------------------------------------
    def _build_blocking(self, key, builder):
        with self._lock:
            ev = self._building.get(key)
            mine = ev is None
            if mine:
                ev = self._building[key] = threading.Event()
        if not mine:
            ev.wait(timeout=60)               # someone else is already building
            value, _ = self.peek(key)
            if value is not None:
                return value
            return builder()                  # their build failed; do it ourselves
        try:
            value = builder()
            self.put(key, value)
            return value
        finally:
            with self._lock:
                self._building.pop(key, None)
            ev.set()

    def _refresh_async(self, key, builder):
        with self._lock:
            if key in self._building:
                return                        # already being rebuilt
            self._building[key] = threading.Event()

        def run():
            try:
                with self._sem:
                    value = builder()
                self.put(key, value)
            except Exception as e:
                print(f"  ! background refresh failed for {key}: {str(e)[:70]}")
            finally:
                with self._lock:
                    ev = self._building.pop(key, None)
                if ev:
                    ev.set()

        threading.Thread(target=run, daemon=True).start()

    # ------------------------------------------------------------------
    def warm(self, jobs, label="warm"):
        """jobs: [(key, builder)] built in order on a background thread."""
        def run():
            t0 = time.time()
            for key, builder in jobs:
                try:
                    started = time.time()
                    self.put(key, builder())
                    print(f"  [{label}] {key} ready in {time.time()-started:.1f}s")
                except Exception as e:
                    print(f"  [{label}] {key} FAILED: {str(e)[:70]}")
            print(f"  [{label}] done in {time.time()-t0:.1f}s")
        threading.Thread(target=run, daemon=True).start()
