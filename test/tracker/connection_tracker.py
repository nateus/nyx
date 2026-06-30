import time
import unittest

from nyx.tracker import ConnectionTracker
import nyx.traffic

from stem.util import connection

try:
  # added in python 3.3
  from unittest.mock import Mock, patch
except ImportError:
  from mock import Mock, patch

STEM_CONNECTIONS = [
  connection.Connection('127.0.0.1', 3531, '75.119.206.243', 22, 'tcp', False),
  connection.Connection('127.0.0.1', 1766, '86.59.30.40', 443, 'tcp', False),
  connection.Connection('127.0.0.1', 1059, '74.125.28.106', 80, 'tcp', False)
]


class TestConnectionTracker(unittest.TestCase):
  @patch('nyx.tracker.tor_controller')
  @patch('nyx.tracker.connection.get_connections')
  @patch('nyx.tracker.system', Mock(return_value = Mock()))
  @patch('stem.util.proc.is_available', Mock(return_value = False))
  @patch('nyx.tracker.connection.system_resolvers', Mock(return_value = [connection.Resolver.NETSTAT]))
  def test_fetching_connections(self, get_value_mock, tor_controller_mock):
    tor_controller_mock().get_pid.return_value = 12345
    tor_controller_mock().get_conf.return_value = '0'
    get_value_mock.return_value = STEM_CONNECTIONS

    with ConnectionTracker(0.04) as daemon:
      time.sleep(0.01)

      connections = daemon.get_value()

      self.assertEqual(1, daemon.run_counter())
      self.assertEqual([conn.remote_address for conn in STEM_CONNECTIONS], [conn.remote_address for conn in connections])

      get_value_mock.return_value = []  # no connection results
      time.sleep(0.05)
      connections = daemon.get_value()

      self.assertEqual(2, daemon.run_counter())
      self.assertEqual([], connections)

  @patch('nyx.tracker.tor_controller')
  @patch('nyx.tracker.connection.get_connections')
  @patch('nyx.tracker.system', Mock(return_value = Mock()))
  @patch('stem.util.proc.is_available', Mock(return_value = False))
  @patch('nyx.tracker.connection.system_resolvers', Mock(return_value = [connection.Resolver.NETSTAT, connection.Resolver.LSOF]))
  def test_resolver_failover(self, get_value_mock, tor_controller_mock):
    tor_controller_mock().get_pid.return_value = 12345
    tor_controller_mock().get_conf.return_value = '0'
    get_value_mock.side_effect = IOError()

    with ConnectionTracker(0.01) as daemon:
      time.sleep(0.015)

      self.assertEqual([connection.Resolver.NETSTAT, connection.Resolver.LSOF], daemon._resolvers)
      self.assertEqual([], daemon.get_value())

      time.sleep(0.025)

      self.assertEqual([connection.Resolver.LSOF], daemon._resolvers)
      self.assertEqual([], daemon.get_value())

      time.sleep(0.035)

      self.assertEqual([], daemon._resolvers)
      self.assertEqual([], daemon.get_value())

      # Now make connection resolution work. We still shouldn't provide any
      # results since we stopped looking.

      get_value_mock.return_value = STEM_CONNECTIONS[:2]
      get_value_mock.side_effect = None
      time.sleep(0.05)
      self.assertEqual([], daemon.get_value())

      # Finally, select a custom resolver. This should cause us to query again
      # reguardless of our prior failures.

      daemon.set_custom_resolver(connection.Resolver.NETSTAT)
      time.sleep(0.05)
      self.assertEqual([conn.remote_address for conn in STEM_CONNECTIONS[:2]], [conn.remote_address for conn in daemon.get_value()])

  @patch('nyx.tracker.tor_controller')
  @patch('nyx.tracker.connection.get_connections')
  @patch('nyx.tracker.system', Mock(return_value = Mock()))
  @patch('stem.util.proc.is_available', Mock(return_value = False))
  @patch('nyx.tracker.connection.system_resolvers', Mock(return_value = [connection.Resolver.NETSTAT]))
  def test_tracking_uptime(self, get_value_mock, tor_controller_mock):
    tor_controller_mock().get_pid.return_value = 12345
    tor_controller_mock().get_conf.return_value = '0'
    get_value_mock.return_value = [STEM_CONNECTIONS[0]]
    first_start_time = time.time()

    with ConnectionTracker(0.04) as daemon:
      time.sleep(0.01)

      connections = daemon.get_value()
      self.assertEqual(1, len(connections))

      self.assertEqual(STEM_CONNECTIONS[0].remote_address, connections[0].remote_address)
      self.assertTrue(first_start_time <= connections[0].start_time <= time.time())
      self.assertTrue(connections[0].is_legacy)

      second_start_time = time.time()
      get_value_mock.return_value = STEM_CONNECTIONS[:2]
      time.sleep(0.05)

      connections = daemon.get_value()
      self.assertEqual(2, len(connections))

      self.assertEqual(STEM_CONNECTIONS[0].remote_address, connections[0].remote_address)
      self.assertTrue(first_start_time < connections[0].start_time < time.time())
      self.assertTrue(connections[0].is_legacy)

      self.assertEqual(STEM_CONNECTIONS[1].remote_address, connections[1].remote_address)
      self.assertTrue(second_start_time < connections[1].start_time < time.time())
      self.assertFalse(connections[1].is_legacy)

  @patch('nyx.tracker.tor_controller')
  @patch('nyx.tracker.connection.get_connections')
  @patch('nyx.tracker.system', Mock(return_value = Mock()))
  @patch('stem.util.proc.is_available', Mock(return_value = False))
  @patch('nyx.tracker.connection.system_resolvers', Mock(return_value = [connection.Resolver.NETSTAT]))
  def test_traffic_samples(self, get_value_mock, tor_controller_mock):
    tor_controller_mock().get_pid.return_value = 12345
    tor_controller_mock().get_conf.return_value = '0'
    get_value_mock.return_value = [STEM_CONNECTIONS[0]]

    daemon = ConnectionTracker(0.04)
    daemon._task(12345, 'tor')

    traffic_resolver = nyx.traffic.ManualTrafficResolver()
    key = nyx.traffic.connection_key(daemon.get_value()[0])
    traffic_resolver.totals = [nyx.traffic.SocketTraffic(key, 100, 20)]
    daemon._traffic_resolver = traffic_resolver

    self.assertEqual([], daemon.get_traffic_samples())

    traffic_resolver.totals = [nyx.traffic.SocketTraffic(key, 180, 35)]
    samples = daemon.get_traffic_samples()

    self.assertEqual(1, len(samples))
    self.assertEqual(daemon.get_value()[0], samples[0].connection)
    self.assertEqual(80, samples[0].bytes_sent)
    self.assertEqual(15, samples[0].bytes_received)
    self.assertEqual(nyx.traffic.TrafficStatus('available', None), daemon.get_traffic_status())

  @patch('nyx.tracker.tor_controller')
  @patch('nyx.tracker.connection.get_connections')
  @patch('nyx.tracker.system', Mock(return_value = Mock()))
  @patch('stem.util.proc.is_available', Mock(return_value = False))
  @patch('nyx.tracker.connection.system_resolvers', Mock(return_value = [connection.Resolver.NETSTAT]))
  def test_traffic_samples_match_remote_endpoint(self, get_value_mock, tor_controller_mock):
    tor_controller_mock().get_pid.return_value = 12345
    tor_controller_mock().get_conf.return_value = '0'
    get_value_mock.return_value = [STEM_CONNECTIONS[0]]

    daemon = ConnectionTracker(0.04)
    daemon._task(12345, 'tor')

    traffic_resolver = nyx.traffic.ManualTrafficResolver()
    _, local_port, remote_address, remote_port, protocol = nyx.traffic.connection_key(daemon.get_value()[0])
    bcc_key = ('0.0.0.0', local_port, remote_address, remote_port, protocol)
    traffic_resolver.totals = [nyx.traffic.SocketTraffic(bcc_key, 100, 20)]
    daemon._traffic_resolver = traffic_resolver

    self.assertEqual([], daemon.get_traffic_samples())

    traffic_resolver.totals = [nyx.traffic.SocketTraffic(bcc_key, 180, 35)]
    samples = daemon.get_traffic_samples()

    self.assertEqual(1, len(samples))
    self.assertEqual(daemon.get_value()[0], samples[0].connection)
    self.assertEqual(80, samples[0].bytes_sent)
    self.assertEqual(15, samples[0].bytes_received)
