# coding: utf-8
import json
import os
import time

from graphite_api._vendor import whisper

from . import TestCase, WHISPER_DIR


class RenderTest(TestCase):
    db = os.path.join(WHISPER_DIR, 'test.wsp')
    url = '/render'

    def create_db(self):
        whisper.create(self.db, [(1, 60)])

        self.ts = int(time.time())
        whisper.update(self.db, 0.5, self.ts - 2)
        whisper.update(self.db, 0.4, self.ts - 1)
        whisper.update(self.db, 0.6, self.ts)

    def test_render_view(self):
        response = self.app.get(self.url, query_string={'target': 'test',
                                                        'format': 'json'})
        self.assertEqual(json.loads(response.data.decode('utf-8')), [])

        response = self.app.get(self.url, query_string={'target': 'test'})
        self.assertEqual(response.headers['Content-Type'], 'image/png')

        self.create_db()
        response = self.app.get(self.url, query_string={'target': 'test',
                                                        'format': 'json'})
        data = json.loads(response.data.decode('utf-8'))
        end = data[0]['datapoints'][-4:]
        try:
            self.assertEqual(
                end, [[None, self.ts - 3], [0.5, self.ts - 2],
                      [0.4, self.ts - 1], [0.6, self.ts]])
        except AssertionError:
            self.assertEqual(
                end, [[0.5, self.ts - 2], [0.4, self.ts - 1],
                      [0.6, self.ts], [None, self.ts + 1]])

        response = self.app.get(self.url, query_string={'target': 'test',
                                                        'maxDataPoints': 2,
                                                        'format': 'json'})
        data = json.loads(response.data.decode('utf-8'))
        # 1 is a time race cond
        self.assertTrue(len(data[0]['datapoints']) in [1, 2])

        response = self.app.get(self.url, query_string={'target': 'test',
                                                        'maxDataPoints': 200,
                                                        'format': 'json'})
        data = json.loads(response.data.decode('utf-8'))
        self.assertEqual(len(data[0]['datapoints']), 60)

    def test_render_constant_line(self):
        response = self.app.get(self.url, query_string={
            'target': 'constantLine(12)'})
        self.assertEqual(response.headers['Content-Type'], 'image/png')

        response = self.app.get(self.url, query_string={
            'target': 'constantLine(12)', 'format': 'json'})
        data = json.loads(response.data.decode('utf-8'))[0]['datapoints']
        self.assertEqual(len(data), 2)
        for point, ts in data:
            self.assertEqual(point, 12)

        response = self.app.get(self.url, query_string={
            'target': 'constantLine(12)', 'format': 'json',
            'maxDataPoints': 12})
        data = json.loads(response.data.decode('utf-8'))[0]['datapoints']
        self.assertEqual(len(data), 2)
        for point, ts in data:
            self.assertEqual(point, 12)

    def test_float_maxdatapoints(self):
        response = self.app.get(self.url, query_string={
            'target': 'sin("foo")', 'format': 'json',
            'maxDataPoints': 5.5})  # rounded to int
        data = json.loads(response.data.decode('utf-8'))[0]['datapoints']
        self.assertEqual(len(data), 5)

    def test_constantline_pathexpr(self):
        response = self.app.get(self.url, query_string={
            'target': 'sumSeries(constantLine(12), constantLine(5))',
            'format': 'json',
        })
        data = json.loads(response.data.decode('utf-8'))[0]['datapoints']
        self.assertEqual([d[0] for d in data], [17, 17])

    def test_area_between(self):
        response = self.app.get(self.url, query_string={
            'target': ['areaBetween(sin("foo"), sin("bar", 2))'],
            'format': 'json',
        })
        data = json.loads(response.data.decode('utf-8'))
        self.assertEqual(len(data), 2)

    def test_sumseries(self):
        response = self.app.get(self.url, query_string={
            'target': ['sumSeries(sin("foo"), sin("bar", 2))',
                       'sin("baz", 3)'],
            'format': 'json',
        })
        data = json.loads(response.data.decode('utf-8'))
        agg = {}
        for series in data:
            agg[series['target']] = series['datapoints']
        for index, value in enumerate(agg['baz']):
            self.assertEqual(value, agg['sumSeries(sin(bar),sin(foo))'][index])

        response = self.app.get(self.url, query_string={
            'target': ['sumSeries(sin("foo"), sin("bar", 2))',
                       'sin("baz", 3)'],
            'format': 'json',
            'maxDataPoints': 100,
        })
        data = json.loads(response.data.decode('utf-8'))
        agg = {}
        for series in data:
            self.assertTrue(len(series['datapoints']) <= 100)
            agg[series['target']] = series['datapoints']
        for index, value in enumerate(agg['baz']):
            self.assertEqual(value, agg['sumSeries(sin(bar),sin(foo))'][index])

    def test_correct_timezone(self):
        response = self.app.get(self.url, query_string={
            'target': 'constantLine(12)',
            'format': 'json',
            'from': '07:00_20140226',
            'until': '08:00_20140226',
            # tz is UTC
        })
        data = json.loads(response.data.decode('utf-8'))[0]['datapoints']

        # all the from/until/tz combinations lead to the same window
        expected = [[12, 1393398000], [12, 1393401600]]
        self.assertEqual(data, expected)

        response = self.app.get(self.url, query_string={
            'target': 'constantLine(12)',
            'format': 'json',
            'from': '08:00_20140226',
            'until': '09:00_20140226',
            'tz': 'Europe/Berlin',
        })
        data = json.loads(response.data.decode('utf-8'))[0]['datapoints']
        self.assertEqual(data, expected)

    def test_render_options(self):
        self.create_db()
        db2 = os.path.join(WHISPER_DIR, 'foo.wsp')
        whisper.create(db2, [(1, 60)])
        ts = int(time.time())
        whisper.update(db2, 0.5, ts - 2)

        for qs in [
            {'logBase': 'e'},
            {'logBase': 1},
            {'logBase': 0.5},
            {'margin': -1},
            {'colorList': 'orange,green,blue,#0f0'},
            {'bgcolor': 'orange'},
            {'bgcolor': 'aaabbb'},
            {'bgcolor': '#aaabbb'},
            {'bgcolor': '#aaabbbff'},
            {'fontBold': 'true'},
            {'title': 'Hellò'},
            {'title': 'true'},
            {'vtitle': 'Hellò'},
            {'title': 'Hellò', 'yAxisSide': 'right'},
            {'uniqueLegend': 'true', '_expr': 'secondYAxis({0})'},
            {'uniqueLegend': 'true', 'vtitleRight': 'foo',
             '_expr': 'secondYAxis({0})'},
            {'graphOnly': 'true', 'yUnitSystem': 'si'},
            {'lineMode': 'staircase'},
            {'lineMode': 'slope'},
            {'lineMode': 'connected'},
            {'min': 1, 'max': 1, 'thickness': 2, 'yUnitSystem': 'welp'},
            {'yMax': 5, 'yLimit': 0.5, 'yStep': 0.1},
            {'yMax': 'max', 'yUnitSystem': 'binary'},
            {'areaMode': 'stacked', '_expr': 'stacked({0})'},
            {'lineMode': 'staircase', '_expr': 'stacked({0})'},
            {'areaMode': 'first', '_expr': 'stacked({0})'},
            {'areaMode': 'all', '_expr': 'stacked({0})'},
            {'areaMode': 'stacked', 'areaAlpha': 0.5, '_expr': 'stacked({0})'},
            {'areaMode': 'stacked', 'areaAlpha': 'a', '_expr': 'stacked({0})'},
            {'_expr': 'dashed(lineWidth({0}, 5))'},
            {'target': 'areaBetween(*)'},
            {'drawNullAsZero': 'true'},
            {'_expr': 'drawAsInfinite({0})'},
            {'graphType': 'pie', 'pieMode': 'average', 'title': 'Pie'},
            {'graphType': 'pie', 'pieMode': 'average', 'hideLegend': 'true'},
            {'graphType': 'pie', 'pieMode': 'average', 'valueLabels': 'none'},
            {'graphType': 'pie', 'pieMode': 'average',
             'valueLabels': 'number'},
            {'graphType': 'pie', 'pieMode': 'average', 'pieLabels': 'rotated'},
        ]:
            if qs.setdefault('target', ['foo', 'test']) == ['foo', 'test']:
                if '_expr' in qs:
                    expr = qs.pop('_expr')
                    qs['target'] = [expr.format(t) for t in qs['target']]
            response = self.app.get(self.url, query_string=qs)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['Content-Type'], 'image/png')

        for qs in [
            {'bgcolor': 'foo'},
        ]:
            qs['target'] = 'test'
            with self.assertRaises(ValueError):
                response = self.app.get(self.url, query_string=qs)

        for qs in [
            {'lineMode': 'stacked'},
        ]:
            qs['target'] = 'test'
            with self.assertRaises(AssertionError):
                response = self.app.get(self.url, query_string=qs)

    def test_render_validation(self):
        whisper.create(self.db, [(1, 60)])

        response = self.app.get(self.url)
        self.assertJSON(response, {'errors': {
            'target': 'This parameter is required.'}}, status_code=400)

        response = self.app.get(self.url, query_string={'graphType': 'foo',
                                                        'target': 'test'})
        self.assertJSON(response, {'errors': {
            'graphType': "Invalid graphType 'foo', must be one of 'line', "
            "'pie'."}}, status_code=400)

        response = self.app.get(self.url, query_string={'maxDataPoints': 'foo',
                                                        'target': 'test'})
        self.assertJSON(response, {'errors': {
            'maxDataPoints': 'Must be an integer.'}}, status_code=400)

        response = self.app.get(self.url, query_string={
            'from': '21:2020140313',
            'until': '21:2020140313',
            'target': 'test'})
        self.assertJSON(response, {'errors': {
            'from': 'Invalid empty time range',
            'until': 'Invalid empty time range',
        }}, status_code=400)

        response = self.app.get(self.url, query_string={
            'target': 'foo',
            'width': 100,
            'thickness': '1.5',
            'fontBold': 'true',
            'fontItalic': 'default',
        })
        self.assertEqual(response.status_code, 200)

        response = self.app.get(self.url, query_string={
            'target': 'foo', 'tz': 'Europe/Lausanne'})
        self.assertJSON(response, {'errors': {
            'tz': "Unknown timezone: 'Europe/Lausanne'.",
        }}, status_code=400)

        response = self.app.get(self.url, query_string={'target': 'test:aa',
                                                        'graphType': 'pie'})
        self.assertJSON(response, {'errors': {
            'target': "Invalid target: 'test:aa'.",
        }}, status_code=400)

        response = self.app.get(self.url, query_string={
            'target': ['test', 'foo:1.2'], 'graphType': 'pie'})
        self.assertEqual(response.status_code, 200)

        response = self.app.get(self.url, query_string={'target': ['test',
                                                                   '']})
        self.assertEqual(response.status_code, 200)

        response = self.app.get(self.url, query_string={'target': 'test',
                                                        'format': 'csv'})
        lines = response.data.decode('utf-8').strip().split('\n')
        self.assertEqual(len(lines), 60)
        self.assertFalse(any([l.strip().split(',')[2] for l in lines]))

        response = self.app.get(self.url, query_string={'target': 'test',
                                                        'format': 'svg',
                                                        'jsonp': 'foo'})
        jsonpsvg = response.data.decode('utf-8')
        self.assertTrue(jsonpsvg.startswith('foo("<?xml version=\\"1.0\\"'))
        self.assertTrue(jsonpsvg.endswith('</script>\\n</svg>")'))

        response = self.app.get(self.url, query_string={'target': 'test',
                                                        'format': 'svg'})
        svg = response.data.decode('utf-8')
        self.assertTrue(svg.startswith('<?xml version="1.0"'))

        response = self.app.get(self.url, query_string={
            'target': 'sum(test)',
        })
        self.assertEqual(response.status_code, 200)

        response = self.app.get(self.url, query_string={
            'target': ['sinFunction("a test", 2)',
                       'sinFunction("other test", 2.1)',
                       'sinFunction("other test", 2e1)'],
        })
        self.assertEqual(response.status_code, 200)

        response = self.app.get(self.url, query_string={
            'target': ['percentileOfSeries(sin("foo bar"), 95, true)']
        })
        self.assertEqual(response.status_code, 200)

    def test_raw_data(self):
        whisper.create(self.db, [(1, 60)])

        response = self.app.get(self.url, query_string={'rawData': '1',
                                                        'target': 'test'})
        info, data = response.data.decode('utf-8').strip().split('|', 1)
        path, start, stop, step = info.split(',')
        datapoints = data.split(',')
        try:
            self.assertEqual(datapoints, ['None'] * 60)
            self.assertEqual(int(stop) - int(start), 60)
        except AssertionError:
            self.assertEqual(datapoints, ['None'] * 59)
            self.assertEqual(int(stop) - int(start), 59)
        self.assertEqual(path, 'test')
        self.assertEqual(int(step), 1)

    def test_jsonp(self):
        whisper.create(self.db, [(1, 60)])

        start = int(time.time()) - 59
        response = self.app.get(self.url, query_string={'format': 'json',
                                                        'jsonp': 'foo',
                                                        'target': 'test'})
        data = response.data.decode('utf-8')
        self.assertTrue(data.startswith('foo('))
        data = json.loads(data[4:-1])
        try:
            self.assertEqual(data, [{'datapoints': [
                [None, start + i] for i in range(60)
            ], 'target': 'test'}])
        except AssertionError:  # Race condition when time overlaps a second
            self.assertEqual(data, [{'datapoints': [
                [None, start + i + 1] for i in range(60)
            ], 'target': 'test'}])
