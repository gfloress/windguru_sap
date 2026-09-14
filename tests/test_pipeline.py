import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import collector
from pipeline import evaluate_latest, notify_changed
from rules_engine import Metrics, Verdict, classify
from notifiers import Pushover


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        collector.init_db(self.conn)
        self.plugin = types.ModuleType('test_rules')
        self.plugin.WIND_RELEVANT_KMH = 10
        self.plugin.classify = Mock(return_value=Verdict('Bom'))
        sys.modules['test_rules'] = self.plugin
        self.notifier = Mock()

    def tearDown(self):
        self.conn.close()
        del sys.modules['test_rules']

    def metrics(self, speed=5, direction=180):
        return Metrics(speed, 15, direction, 1, 10, 180, 1, 10, 180)

    def test_wind_gate_and_boundary(self):
        classify(self.metrics(), 'test_rules')
        self.assertIsNone(self.plugin.classify.call_args.args[0].vento_direcao_graus)
        classify(self.metrics(10), 'test_rules')
        self.assertEqual(self.plugin.classify.call_args.args[0].vento_direcao_graus, 180)
        self.assertIsNone(classify(self.metrics(None), 'test_rules'))
        self.assertIsNone(classify(self.metrics(10, None), 'test_rules'))
        self.assertIsNone(classify(self.metrics(float('nan')), 'test_rules'))

    def test_pending_rules(self):
        self.assertIsNone(classify(self.metrics()))

    def test_changes_only_and_failure_retries(self):
        for label, expected in [('Bom', True), ('Bom', False), ('Ruim', True), ('Bom', True)]:
            self.assertEqual(notify_changed(self.conn, 'spot', Verdict(label), 'hora', self.notifier), expected)
        self.notifier.send.side_effect = RuntimeError('offline')
        with self.assertRaises(RuntimeError):
            notify_changed(self.conn, 'spot', Verdict('Classico'), 'hora', self.notifier)
        self.assertEqual(self.conn.execute('SELECT classificacao FROM ultimo_estado_notificado').fetchone()[0], 'Bom')
        self.notifier.send.side_effect = None
        self.assertTrue(notify_changed(self.conn, 'spot', Verdict('Classico'), 'hora', self.notifier))

    def test_persistence_across_connections(self):
        with tempfile.TemporaryDirectory() as directory:
            path = directory + '/state.db'
            with sqlite3.connect(path) as first:
                notify_changed(first, 'spot', Verdict('Bom'), 'hora', self.notifier)
            first.close()
            with sqlite3.connect(path) as second:
                self.assertFalse(notify_changed(second, 'spot', Verdict('Bom'), 'hora', self.notifier))
            second.close()

    def data(self):
        marine = {'time': ['2026-09-14T12:00', '2026-09-14T13:00']}
        for key in ['wave_height', 'wave_period', 'wave_direction', 'swell_wave_height', 'swell_wave_period', 'swell_wave_direction']:
            marine[key] = [1, 2]
        wind = {'time': list(reversed(marine['time'])), 'wind_speed_10m': [20, 5],
                'wind_direction_10m': [90, 180], 'wind_gusts_10m': [25, 7]}
        return marine, wind

    def test_timestamp_join(self):
        collector.merge_and_save(self.conn, *self.data())
        rows = self.conn.execute('SELECT vento_velocidade_kmh FROM previsoes_brutas ORDER BY horario_previsto').fetchall()
        self.assertEqual(rows, [(5,), (20,)])

    def test_bad_alignment_no_partial_write(self):
        marine, wind = self.data()
        wind['time'][0] = '2026-09-14T14:00'
        with self.assertRaises(ValueError):
            collector.merge_and_save(self.conn, marine, wind)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM previsoes_brutas').fetchone()[0], 0)

    def test_current_hour_dry_run_and_stale(self):
        collector.merge_and_save(self.conn, *self.data())
        now = datetime(2026, 9, 14, 15, 20, tzinfo=timezone.utc)
        self.conn.execute('UPDATE previsoes_brutas SET coletado_em=?', (now.isoformat(),))
        self.conn.commit()
        kwargs = dict(now=now, plugin='test_rules', notifier=self.notifier)
        self.assertFalse(evaluate_latest(self.conn, collector.SPOT_NAME, collector.TIMEZONE, dry_run=True, **kwargs))
        self.notifier.send.assert_not_called()
        self.assertTrue(evaluate_latest(self.conn, collector.SPOT_NAME, collector.TIMEZONE, dry_run=False, **kwargs))
        self.assertIn('12:00', self.notifier.send.call_args.args[1])
        self.conn.execute("UPDATE previsoes_brutas SET coletado_em='2020-01-01T00:00:00+00:00'")
        self.conn.commit()
        with self.assertRaises(ValueError):
            evaluate_latest(self.conn, collector.SPOT_NAME, collector.TIMEZONE, **kwargs)

    @patch.dict('os.environ', {'PUSHOVER_APP_TOKEN': 'fake', 'PUSHOVER_USER_KEY': 'fake'})
    @patch('notifiers.requests.post')
    def test_provider_requires_ack(self, post):
        post.return_value.json.return_value = {'status': 0}
        with self.assertRaises(RuntimeError):
            Pushover().send('title', 'message')
        post.return_value.json.return_value = {'status': 1}
        Pushover().send('title', 'message')


if __name__ == '__main__':
    unittest.main()
