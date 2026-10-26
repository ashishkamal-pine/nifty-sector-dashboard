import io
import json
import unittest
from unittest.mock import patch

import app
from store import Store


class Request(app.Handler):
    """Exercise the real route without opening sockets or fetching market data."""

    def __init__(self, path):
        self.path = path
        self.wfile = io.BytesIO()
        self.headers_sent = {}

    def send_response(self, code):
        self.code = code

    def send_header(self, name, value):
        self.headers_sent[name] = value

    def end_headers(self):
        pass


class RotationRefreshTests(unittest.TestCase):
    def request(self, query):
        req = Request('/api/rrg.json?' + query)
        req.do_GET()
        self.assertEqual(req.code, 200)
        self.assertEqual(req.headers_sent['Cache-Control'], 'no-store')
        return json.loads(req.wfile.getvalue())

    def test_expired_positions_are_rebuilt_in_the_same_response(self):
        for scope, name, bench in [('sectors', None, 'nifty'),
                                   ('sector', 'IT', 'nifty'),
                                   ('sector', 'IT', 'sector')]:
            for tf in ('daily', 'weekly'):
                with self.subTest(scope=scope, tf=tf, bench=bench):
                    cache = Store()
                    key = ('rrg', scope, name, tf, '12', bench)
                    with patch('store.time.time', return_value=1000):
                        cache.put(key, {'points': [{'quadrant': 'Lagging'}]})
                    fresh = {'points': [{'quadrant': 'Leading'}], 'timeframe': tf}
                    query = 'scope=%s&tf=%s&bench=%s' % (scope, tf, bench)
                    if name:
                        query += '&name=' + name
                    with patch.object(app, 'STORE', cache), \
                         patch('store.time.time', return_value=1121), \
                         patch.object(app, 'build_rrg', return_value=fresh) as build:
                        result = self.request(query)
                    self.assertEqual(result['points'], fresh['points'])
                    self.assertEqual(result['cache']['state'], 'built')
                    build.assert_called_once_with(scope=scope, name=name,
                                                  timeframe=tf, tail='12', bench=bench)

    def test_fresh_cache_and_manual_force_still_work(self):
        cache = Store()
        key = ('rrg', 'sectors', None, 'weekly', '12', 'nifty')
        with patch('store.time.time', return_value=1000):
            cache.put(key, {'points': [{'quadrant': 'Weakening'}]})
        with patch.object(app, 'STORE', cache), \
             patch('store.time.time', return_value=1010), \
             patch.object(app, 'build_rrg', return_value={'points': []}) as build:
            result = self.request('tf=weekly')
            self.assertEqual(result['points'][0]['quadrant'], 'Weakening')
            build.assert_not_called()
            self.request('tf=weekly&force=1')
            build.assert_called_once()

    def test_other_dashboard_caches_keep_background_refresh(self):
        cache = Store()
        old = {'sectors': ['cached fixture']}
        with patch('store.time.time', return_value=1000):
            cache.put('sectors', old)
        with patch('store.time.time', return_value=1031), \
             patch.object(cache, '_refresh_async') as refresh:
            build = lambda: {'sectors': []}
            result, _, state = cache.get('sectors', build, fresh=30)
        self.assertEqual(result, old)
        self.assertEqual(state, 'stale')
        refresh.assert_called_once_with('sectors', build)


if __name__ == '__main__':
    unittest.main()
