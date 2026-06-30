"""
Unit tests for nyx.traffic.
"""

import unittest

import nyx.traffic

from stem.util import connection

try:
  from unittest.mock import Mock, patch
except ImportError:
  from mock import Mock, patch


CONNECTION = connection.Connection('127.0.0.1', 3531, '75.119.206.243', 22, 'tcp', False)
KEY = nyx.traffic.connection_key(CONNECTION)


class TestTraffic(unittest.TestCase):
  def test_connection_key(self):
    self.assertEqual(('127.0.0.1', 3531, '75.119.206.243', 22, 'tcp'), KEY)

  def test_unavailable_reason(self):
    self.assertEqual('bcc_missing', nyx.traffic.unavailable_reason(nyx.traffic.TrafficStatus('unavailable', 'bcc_missing')))
    self.assertEqual('sample_unavailable_with_available_status', nyx.traffic.unavailable_reason(nyx.traffic.TrafficStatus('available', None)))
    self.assertEqual('unknown', nyx.traffic.unavailable_reason(nyx.traffic.TrafficStatus('unavailable', None)))

  def test_unavailable_resolver_has_reason(self):
    resolver = nyx.traffic.UnavailableTrafficResolver(None)
    self.assertEqual(nyx.traffic.TrafficStatus('unavailable', 'unavailable'), resolver.status())

  def test_delta_resolver(self):
    resolver = nyx.traffic.ManualTrafficResolver()
    resolver.totals = [nyx.traffic.SocketTraffic(KEY, 100, 20)]

    self.assertEqual([], resolver.sample([CONNECTION]))

    resolver.totals = [nyx.traffic.SocketTraffic(KEY, 175, 25)]
    self.assertEqual([nyx.traffic.SocketTraffic(KEY, 75, 5)], resolver.sample([CONNECTION]))

  def test_delta_resolver_ignores_reset_counters(self):
    resolver = nyx.traffic.ManualTrafficResolver()
    resolver.totals = [nyx.traffic.SocketTraffic(KEY, 100, 20)]
    resolver.sample([CONNECTION])

    resolver.totals = [nyx.traffic.SocketTraffic(KEY, 50, 10)]
    self.assertEqual([], resolver.sample([CONNECTION]))

  @patch('nyx.traffic.platform.system', Mock(return_value = 'Windows'))
  def test_bcc_resolver_reports_unsupported_platform(self):
    resolver = nyx.traffic.BccTrafficResolver()
    self.assertEqual(nyx.traffic.TrafficStatus('unavailable', 'unsupported_platform'), resolver.status())
    self.assertEqual(None, resolver.sample([CONNECTION]))

  @patch('nyx.traffic.platform.system', Mock(return_value = 'Windows'))
  def test_best_resolver_falls_back(self):
    with patch.dict(nyx.traffic.CONFIG, {'traffic_resolver': 'auto'}):
      resolver = nyx.traffic.best_resolver()

    self.assertEqual(nyx.traffic.TrafficStatus('unavailable', 'unsupported_platform'), resolver.status())
