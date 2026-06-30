# Copyright 2026, The Tor Project
# See LICENSE for licensing information

"""
Headless collector for persisting Tor runtime history into Nyx's cache.
"""

import threading
import time

import stem.connection
import stem.response.events
from stem.control import EventType
from stem.util import conf, log

import nyx
import nyx.tracker


def conf_handler(key, value):
  if key == 'collector_interval':
    return max(1, value)
  elif key == 'collector_retention_days':
    return max(1, value)


CONFIG = conf.config_dict('nyx', {
  'collector_enabled': True,
  'collector_interval': 1,
  'collector_retention_days': 30,
  'collector_log_events': 'NOTICE,WARN,ERR',
  'connection_show_traffic': True,
  'traffic_top_limit': 50,
}, conf_handler)


class Collector(object):
  def __init__(self, controller, cache = None):
    self._controller = controller
    self._cache = cache if cache else nyx.cache()
    self._events = []
    self._event = threading.Event()
    self._is_running = False

  def start(self):
    self._is_running = True

    with self._cache.write() as writer:
      writer.set_collector_status('running', 'true')
      writer.set_collector_status('started_at', str(time.time()))

    self._listen_for(EventType.BW)

    for event_type in _configured_log_events():
      self._listen_for(event_type)

  def stop(self):
    self._is_running = False

    for event_type in self._events:
      try:
        self._controller.remove_event_listener(self._record_event, event_type)
      except TypeError:
        self._controller.remove_event_listener(self._record_event)
      except Exception:
        pass

    with self._cache.write() as writer:
      writer.set_collector_status('running', 'false')
      writer.set_collector_status('stopped_at', str(time.time()))

    self._event.set()

  def run(self):
    self.start()

    try:
      while self._is_running and self._controller.is_alive():
        self._event.wait(CONFIG['collector_interval'])
        self._record_connection_traffic()
        self._trim_history()
    finally:
      self.stop()

  def _listen_for(self, event_type):
    self._controller.add_event_listener(self._record_event, event_type)
    self._events.append(event_type)

  def _record_event(self, event):
    try:
      with self._cache.write() as writer:
        if isinstance(event, stem.response.events.BandwidthEvent):
          writer.record_bandwidth_sample(event.read, event.written, event.arrived_at)
        elif isinstance(event, stem.response.events.LogEvent):
          writer.record_tor_log_event(event.type, event.message, event.arrived_at)
    except Exception as exc:
      with self._cache.write() as writer:
        writer.set_collector_status('last_error', str(exc))

  def _trim_history(self):
    cutoff = time.time() - (CONFIG['collector_retention_days'] * 86400)

    with self._cache.write() as writer:
      writer.trim_collector_history(cutoff)

  def _record_connection_traffic(self):
    tracker = nyx.tracker.get_connection_tracker()
    samples = tracker.get_traffic_samples()
    status = tracker.get_traffic_status()

    if samples is None:
      with self._cache.write() as writer:
        writer.set_collector_status('traffic_counters', 'unavailable')
        writer.set_collector_status('traffic_counters_reason', nyx.traffic.unavailable_reason(status))

      return

    consensus_tracker = nyx.tracker.get_consensus_tracker()

    with self._cache.write() as writer:
      writer.set_collector_status('traffic_counters', 'available')
      writer.set_collector_status('traffic_counters_reason', '')

      for sample in samples:
        conn = sample.connection
        relays = consensus_tracker.get_relay_fingerprints(conn.remote_address)
        fingerprint = relays.get(conn.remote_port) if relays else None

        if not fingerprint:
          continue

        nickname = consensus_tracker.get_relay_nickname(fingerprint)
        country = self._controller.get_info('ip-to-country/%s' % conn.remote_address, None)
        writer.record_ip_traffic(conn.remote_address, fingerprint, nickname, country, sample.bytes_sent, sample.bytes_received)


def _configured_log_events():
  event_types = []

  for event_type in CONFIG['collector_log_events'].split(','):
    event_type = event_type.strip().upper()

    if event_type:
      event_types.append(event_type)

  return event_types


@nyx.uses_settings
def main(config):
  if not CONFIG['collector_enabled']:
    log.notice('nyx-collector is disabled by configuration')
    return

  controller_password = config.get('password', None)
  controller = stem.connection.connect(password = controller_password)

  if controller is None:
    raise SystemExit(1)

  collector = Collector(controller)

  try:
    collector.run()
  except KeyboardInterrupt:
    pass
