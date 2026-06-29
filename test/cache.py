"""
Unit tests for nyx.cache.
"""

import re
import os
<<<<<<< HEAD
=======
import sqlite3
>>>>>>> bc3f1cce9797859779019df302632dfdbbc6ca96
import tempfile
import time
import unittest

import nyx

try:
  # added in python 3.3
  from unittest.mock import Mock, patch
except ImportError:
  from mock import Mock, patch


class TestCache(unittest.TestCase):
  def setUp(self):
    nyx.CACHE = None  # drop cached database reference

  @patch('nyx.data_directory', Mock(return_value = None))
  def test_memory_cache(self):
    """
    Create a cache in memory.
    """

    cache = nyx.cache()
    self.assertEqual((0, 'main', ''), cache._query('PRAGMA database_list').fetchone())

    with cache.write() as writer:
      writer.record_relay('3EA8E960F6B94CE30062AA8EF02894C00F8D1E66', '208.113.165.162', 1443, 'caersidi')

    self.assertEqual('caersidi', cache.relay_nickname('3EA8E960F6B94CE30062AA8EF02894C00F8D1E66'))

  def test_file_cache(self):
    """
    Create a new cache file, and ensure we can reload cached results.
    """

    tmp_fd, tmp_path = tempfile.mkstemp(suffix = '.sqlite')
    os.close(tmp_fd)

    try:
      with patch('nyx.data_directory', Mock(return_value = tmp_path)):
        cache = nyx.cache()
        self.assertEqual((0, 'main', tmp_path), cache._query('PRAGMA database_list').fetchone())

        with cache.write() as writer:
          writer.record_relay('3EA8E960F6B94CE30062AA8EF02894C00F8D1E66', '208.113.165.162', 1443, 'caersidi')

        nyx.CACHE._conn.close()
        nyx.CACHE = None
        cache = nyx.cache()
        self.assertEqual('caersidi', cache.relay_nickname('3EA8E960F6B94CE30062AA8EF02894C00F8D1E66'))
    finally:
      if nyx.CACHE:
        nyx.CACHE._conn.close()
        nyx.CACHE = None

      os.remove(tmp_path)
<<<<<<< HEAD
=======

  def test_schema_migration_preserves_history(self):
    """
    Migrates an existing cache rather than clearing it.
    """

    with tempfile.NamedTemporaryFile(suffix = '.sqlite', delete = False) as tmp:
      cache_path = tmp.name

    try:
      conn = sqlite3.connect(cache_path)
      conn.execute('CREATE TABLE schema(version INTEGER)')
      conn.execute('INSERT INTO schema(version) VALUES (2)')
      conn.execute('CREATE TABLE metadata(relays_updated_at REAL)')
      conn.execute('INSERT INTO metadata(relays_updated_at) VALUES (0.0)')
      conn.execute('CREATE TABLE relays(fingerprint TEXT PRIMARY KEY, address TEXT, or_port INTEGER, nickname TEXT)')
      conn.execute('CREATE INDEX addresses ON relays(address)')
      conn.execute('INSERT INTO relays(fingerprint, address, or_port, nickname) VALUES (?,?,?,?)', ('3EA8E960F6B94CE30062AA8EF02894C00F8D1E66', '208.113.165.162', 1443, 'caersidi'))
      conn.commit()
      conn.close()

      with patch('nyx.data_directory', Mock(return_value = cache_path)):
        cache = nyx.cache()
        self.assertEqual('caersidi', cache.relay_nickname('3EA8E960F6B94CE30062AA8EF02894C00F8D1E66'))
        self.assertEqual(4, cache._query('SELECT version FROM schema').fetchone()[0])
        self.assertEqual([], cache.bandwidth_samples())
    finally:
      if nyx.CACHE:
        nyx.CACHE._conn.close()
        nyx.CACHE = None

      os.remove(cache_path)
>>>>>>> bc3f1cce9797859779019df302632dfdbbc6ca96

  @patch('nyx.data_directory', Mock(return_value = None))
  def test_relays_for_address(self):
    """
    Basic checks for fetching relays by their address.
    """

    cache = nyx.cache()

    with cache.write() as writer:
      writer.record_relay('3EA8E960F6B94CE30062AA8EF02894C00F8D1E66', '208.113.165.162', 1443, 'caersidi1')
      writer.record_relay('9695DFC35FFEB861329B9F1AB04C46397020CE31', '128.31.0.34', 9101, 'moria1')
      writer.record_relay('74A910646BCEEFBCD2E874FC1DC997430F968145', '208.113.165.162', 1543, 'caersidi2')

    self.assertEqual({9101: '9695DFC35FFEB861329B9F1AB04C46397020CE31'}, cache.relays_for_address('128.31.0.34'))
    self.assertEqual({1443: '3EA8E960F6B94CE30062AA8EF02894C00F8D1E66', 1543: '74A910646BCEEFBCD2E874FC1DC997430F968145'}, cache.relays_for_address('208.113.165.162'))

    self.assertEqual({}, cache.relays_for_address('199.254.238.53'))

  @patch('nyx.data_directory', Mock(return_value = None))
  def test_relay_nickname(self):
    """
    Basic checks for registering and fetching nicknames.
    """

    cache = nyx.cache()

    with cache.write() as writer:
      writer.record_relay('3EA8E960F6B94CE30062AA8EF02894C00F8D1E66', '208.113.165.162', 1443, 'caersidi')
      writer.record_relay('9695DFC35FFEB861329B9F1AB04C46397020CE31', '128.31.0.34', 9101, 'moria1')
      writer.record_relay('74A910646BCEEFBCD2E874FC1DC997430F968145', '199.254.238.53', 443, 'longclaw')

    self.assertEqual('moria1', cache.relay_nickname('9695DFC35FFEB861329B9F1AB04C46397020CE31'))
    self.assertEqual('longclaw', cache.relay_nickname('74A910646BCEEFBCD2E874FC1DC997430F968145'))
    self.assertEqual('caersidi', cache.relay_nickname('3EA8E960F6B94CE30062AA8EF02894C00F8D1E66'))

    self.assertEqual(None, cache.relay_nickname('66E1D8F00C49820FE8AA26003EC49B6F069E8AE3'))

  @patch('nyx.data_directory', Mock(return_value = None))
  def test_relay_address(self):
    """
    Basic checks for registering and fetching nicknames.
    """

    cache = nyx.cache()

    with cache.write() as writer:
      writer.record_relay('3EA8E960F6B94CE30062AA8EF02894C00F8D1E66', '208.113.165.162', 1443, 'caersidi')
      writer.record_relay('9695DFC35FFEB861329B9F1AB04C46397020CE31', '128.31.0.34', 9101, 'moria1')
      writer.record_relay('74A910646BCEEFBCD2E874FC1DC997430F968145', '199.254.238.53', 443, 'longclaw')

    self.assertEqual(('128.31.0.34', 9101), cache.relay_address('9695DFC35FFEB861329B9F1AB04C46397020CE31'))
    self.assertEqual(('199.254.238.53', 443), cache.relay_address('74A910646BCEEFBCD2E874FC1DC997430F968145'))
    self.assertEqual(('208.113.165.162', 1443), cache.relay_address('3EA8E960F6B94CE30062AA8EF02894C00F8D1E66'))

    self.assertEqual(None, cache.relay_address('66E1D8F00C49820FE8AA26003EC49B6F069E8AE3'))

  @patch('nyx.data_directory', Mock(return_value = None))
  def test_relays_updated_at(self):
    """
    Basic checks for getting when relay information was last updated.
    """

    before = time.time()
    time.sleep(0.01)

    cache = nyx.cache()

    with cache.write() as writer:
      writer.record_relay('3EA8E960F6B94CE30062AA8EF02894C00F8D1E66', '208.113.165.162', 1443, 'caersidi1')

    time.sleep(0.01)
    after = time.time()

    self.assertTrue(before < cache.relays_updated_at() < after)

  @patch('nyx.data_directory', Mock(return_value = None))
  def test_record_relay_when_updating(self):
    cache = nyx.cache()

    with cache.write() as writer:
      writer.record_relay('3EA8E960F6B94CE30062AA8EF02894C00F8D1E66', '208.113.165.162', 1443, 'caersidi')

    self.assertEqual('caersidi', cache.relay_nickname('3EA8E960F6B94CE30062AA8EF02894C00F8D1E66'))

    with cache.write() as writer:
      writer.record_relay('3EA8E960F6B94CE30062AA8EF02894C00F8D1E66', '128.31.0.34', 9101, 'moria1')

    self.assertEqual('moria1', cache.relay_nickname('3EA8E960F6B94CE30062AA8EF02894C00F8D1E66'))

  @patch('nyx.data_directory', Mock(return_value = None))
<<<<<<< HEAD
=======
  def test_collector_bandwidth_cache(self):
    cache = nyx.cache()

    with cache.write() as writer:
      writer.record_bandwidth_sample(10, 20, 100.0)
      writer.record_bandwidth_sample(30, 15, 101.0)
      writer.record_tor_log_event('NOTICE', 'bootstrapped', 102.0)
      writer.set_collector_status('running', 'true')

    self.assertEqual([(100.0, 10, 20), (101.0, 30, 15)], cache.bandwidth_samples())
    self.assertEqual((30, 101.0), cache.bandwidth_peak('download'))
    self.assertEqual((20, 100.0), cache.bandwidth_peak('upload'))
    self.assertEqual([(102.0, 'NOTICE', 'bootstrapped')], cache.tor_log_events())
    self.assertEqual('true', cache.collector_status('running'))

  @patch('nyx.data_directory', Mock(return_value = None))
>>>>>>> bc3f1cce9797859779019df302632dfdbbc6ca96
  def test_ip_traffic_cache(self):
    cache = nyx.cache()

    with cache.write() as writer:
      writer.record_ip_traffic('75.119.206.243', '3EA8E960F6B94CE30062AA8EF02894C00F8D1E66', 'caersidi', 'de', 100, 20, 10.0)
      writer.record_ip_traffic('75.119.206.243', '3EA8E960F6B94CE30062AA8EF02894C00F8D1E66', 'caersidi', 'de', 50, 5, 20.0)
      writer.record_ip_traffic('86.59.30.40', '9695DFC35FFEB861329B9F1AB04C46397020CE31', 'moria1', 'at', 500, 10, 30.0)
<<<<<<< HEAD
      writer.set_collector_status('traffic_counters_reason', 'bcc_missing')

    self.assertEqual(('75.119.206.243', '3EA8E960F6B94CE30062AA8EF02894C00F8D1E66', 'caersidi', 'de', 150, 25, 10.0, 20.0), cache.ip_traffic('75.119.206.243'))
    self.assertEqual(['86.59.30.40', '75.119.206.243'], [entry[0] for entry in cache.top_ip_traffic()])
    self.assertEqual('bcc_missing', cache.collector_status('traffic_counters_reason'))
=======

    self.assertEqual(('75.119.206.243', '3EA8E960F6B94CE30062AA8EF02894C00F8D1E66', 'caersidi', 'de', 150, 25, 10.0, 20.0), cache.ip_traffic('75.119.206.243'))
    self.assertEqual(['86.59.30.40', '75.119.206.243'], [entry[0] for entry in cache.top_ip_traffic()])

  @patch('nyx.data_directory', Mock(return_value = None))
  def test_collector_retention(self):
    cache = nyx.cache()

    with cache.write() as writer:
      writer.record_bandwidth_sample(10, 20, 100.0)
      writer.record_bandwidth_sample(30, 40, 200.0)
      writer.record_tor_log_event('WARN', 'old', 100.0)
      writer.record_tor_log_event('ERR', 'new', 200.0)
      writer.record_ip_traffic('75.119.206.243', '3EA8E960F6B94CE30062AA8EF02894C00F8D1E66', 'caersidi', 'de', 100, 20, 100.0)
      writer.trim_collector_history(150.0)

    self.assertEqual([(200.0, 30, 40)], cache.bandwidth_samples())
    self.assertEqual([(200.0, 'ERR', 'new')], cache.tor_log_events())
    self.assertEqual(None, cache.ip_traffic('75.119.206.243'))
>>>>>>> bc3f1cce9797859779019df302632dfdbbc6ca96

  @patch('nyx.data_directory', Mock(return_value = None))
  def test_record_relay_when_invalid(self):
    """
    Provide malformed information to record_relay.
    """

    with nyx.cache().write() as writer:
      self.assertRaisesRegexp(ValueError, re.escape("'blarg' isn't a valid fingerprint"), writer.record_relay, 'blarg', '208.113.165.162', 1443, 'caersidi')
      self.assertRaisesRegexp(ValueError, re.escape("'blarg' isn't a valid address"), writer.record_relay, '3EA8E960F6B94CE30062AA8EF02894C00F8D1E66', 'blarg', 1443, 'caersidi')
      self.assertRaisesRegexp(ValueError, re.escape("'blarg' isn't a valid port"), writer.record_relay, '3EA8E960F6B94CE30062AA8EF02894C00F8D1E66', '208.113.165.162', 'blarg', 'caersidi')
      self.assertRaisesRegexp(ValueError, re.escape("'~blarg' isn't a valid nickname"), writer.record_relay, '3EA8E960F6B94CE30062AA8EF02894C00F8D1E66', '208.113.165.162', 1443, '~blarg')
