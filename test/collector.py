"""
Unit tests for nyx.collector.
"""

import unittest

import stem.response.events

import nyx
import nyx.collector

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

