"""
Unit tests for nyx.collector.
"""

import unittest

import stem.response.events

import nyx
import nyx.collector
import nyx.traffic
from nyx.tracker import TrafficSample
from stem.util import connection

try:
  from unittest.mock import Mock, patch
except ImportError:
  from mock import Mock, patch


class BandwidthEvent(stem.response.events.BandwidthEvent):
  def __init__(self, read, written, arrived_at):
    self.read = read
    self.written = written
    self.arrived_at = arrived_at


class LogEvent(stem.response.events.LogEvent):
  def __init__(self, event_type, message, arrived_at):
    self.type = event_type
    self.message = message
    self.arrived_at = arrived_at


class Controller(object):
  def __init__(self):
    self.events = []

  def add_event_listener(self, listener, event_type):
    self.events.append((listener, event_type))

  def is_alive(self):
    return False


class TestCollector(unittest.TestCase):
  def setUp(self):
    nyx.CACHE = None

  @patch('nyx.data_directory', Mock(return_value = None))
  def test_records_bandwidth_and_log_events(self):
    controller = Controller()
    collector = nyx.collector.Collector(controller)
    collector.start()

    collector._record_event(BandwidthEvent(50, 70, 123.0))
    collector._record_event(LogEvent('NOTICE', 'Bootstrapped 100%', 124.0))

    cache = nyx.cache()
    self.assertEqual([(123.0, 50, 70)], cache.bandwidth_samples())
    self.assertEqual([(124.0, 'NOTICE', 'Bootstrapped 100%')], cache.tor_log_events())
    self.assertEqual('true', cache.collector_status('running'))

  @patch('nyx.data_directory', Mock(return_value = None))
  @patch('nyx.collector.time.time', Mock(return_value = 200.0))
  def test_trim_history_uses_configured_retention(self):
    cache = nyx.cache()

    with cache.write() as writer:
      writer.record_bandwidth_sample(1, 2, 100.0)
      writer.record_bandwidth_sample(3, 4, 199.0)

    controller = Controller()
    collector = nyx.collector.Collector(controller, cache)

    with patch.dict(nyx.collector.CONFIG, {'collector_retention_days': 1.0 / 86400}):
      collector._trim_history()

    self.assertEqual([(199.0, 3, 4)], cache.bandwidth_samples())

  @patch('nyx.data_directory', Mock(return_value = None))
  @patch('nyx.tracker.get_connection_tracker')
  @patch('nyx.tracker.get_consensus_tracker')
  def test_records_relay_traffic_only(self, consensus_tracker_mock, connection_tracker_mock):
    relay_conn = connection.Connection('127.0.0.1', 9001, '75.119.206.243', 443, 'tcp', False)
    private_conn = connection.Connection('127.0.0.1', 9001, '192.168.0.20', 443, 'tcp', False)

    connection_tracker_mock().get_traffic_samples.return_value = [
      TrafficSample(relay_conn, 100, 10),
      TrafficSample(private_conn, 999, 1),
    ]

    consensus_tracker_mock().get_relay_fingerprints.side_effect = lambda address: {
      '75.119.206.243': {443: '3EA8E960F6B94CE30062AA8EF02894C00F8D1E66'},
      '192.168.0.20': {},
    }[address]
    consensus_tracker_mock().get_relay_nickname.return_value = 'caersidi'

    controller = Controller()
    controller.get_info = Mock(return_value = 'de')
    collector = nyx.collector.Collector(controller)
    collector._record_connection_traffic()

    cache = nyx.cache()
    self.assertEqual(100, cache.ip_traffic('75.119.206.243')[4])
    self.assertEqual(None, cache.ip_traffic('192.168.0.20'))

  @patch('nyx.data_directory', Mock(return_value = None))
  @patch('nyx.tracker.get_connection_tracker')
  def test_marks_traffic_unavailable(self, connection_tracker_mock):
    connection_tracker_mock().get_traffic_samples.return_value = None
    connection_tracker_mock().get_traffic_status.return_value = nyx.traffic.TrafficStatus('unavailable', 'bcc_missing')

    collector = nyx.collector.Collector(Controller())
    collector._record_connection_traffic()

    self.assertEqual('unavailable', nyx.cache().collector_status('traffic_counters'))
    self.assertEqual('bcc_missing', nyx.cache().collector_status('traffic_counters_reason'))
