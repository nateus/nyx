# Copyright 2026, The Tor Project
# See LICENSE for licensing information

"""
Per-socket traffic measurement backends.
"""

import collections
import os
import platform
import socket
import struct

from stem.util import conf


TrafficStatus = collections.namedtuple('TrafficStatus', [
  'state',
  'reason',
])

SocketTraffic = collections.namedtuple('SocketTraffic', [
  'key',
  'bytes_sent',
  'bytes_received',
])

CONFIG = conf.config_dict('nyx', {
  'traffic_resolver': 'auto',
})


def connection_key(conn):
  return (
    conn.local_address,
    int(conn.local_port),
    conn.remote_address,
    int(conn.remote_port),
    conn.protocol,
  )


def best_resolver():
  resolver = CONFIG['traffic_resolver'].strip().lower()

  if resolver in ('auto', 'bcc'):
    bcc_resolver = BccTrafficResolver()
    bcc_status = bcc_resolver.status()

    if bcc_status.state == 'available' or resolver == 'bcc':
      return bcc_resolver

    return UnavailableTrafficResolver(bcc_status.reason)

  return UnavailableTrafficResolver('no_supported_backend')


class TrafficResolver(object):
  def status(self):
    return TrafficStatus('unavailable', 'not_implemented')

  def sample(self, connections):
    return None


class UnavailableTrafficResolver(TrafficResolver):
  def __init__(self, reason):
    self._status = TrafficStatus('unavailable', reason)

  def status(self):
    return self._status


class DeltaTrafficResolver(TrafficResolver):
  def __init__(self):
    self._last_totals = {}

  def status(self):
    return TrafficStatus('available', None)

  def _read_totals(self):
    raise NotImplementedError('should be implemented by subclasses')

  def sample(self, connections):
    totals = dict([(entry.key, entry) for entry in self._read_totals()])
    samples = []

    for conn in connections:
      key = connection_key(conn)
      current = totals.get(key)

      if not current:
        continue

      previous = self._last_totals.get(key)

      if previous:
        sent_delta = current.bytes_sent - previous.bytes_sent
        received_delta = current.bytes_received - previous.bytes_received

        if sent_delta >= 0 and received_delta >= 0 and (sent_delta or received_delta):
          samples.append(SocketTraffic(key, sent_delta, received_delta))

    self._last_totals = totals
    return samples


class ManualTrafficResolver(DeltaTrafficResolver):
  """
  Test helper backed by caller-provided cumulative socket totals.
  """

  def __init__(self):
    super(ManualTrafficResolver, self).__init__()
    self.totals = []

  def _read_totals(self):
    return self.totals


class BccTrafficResolver(DeltaTrafficResolver):
  """
  Linux eBPF/BCC backend. This is optional and only active when BCC and kernel
  permissions are available.
  """

  _BPF_PROGRAM = r"""
#include <uapi/linux/ptrace.h>
#include <linux/in.h>
#include <net/sock.h>

struct socket_key_t {
  u32 saddr;
  u32 daddr;
  u16 sport;
  u16 dport;
  u8 protocol;
};

struct traffic_t {
  u64 sent;
  u64 received;
};

BPF_HASH(traffic, struct socket_key_t, struct traffic_t);

static int fill_key(struct sock *sk, struct socket_key_t *key) {
  u16 family = sk->__sk_common.skc_family;

  if (family != AF_INET) {
    return 0;
  }

  key->saddr = sk->__sk_common.skc_rcv_saddr;
  key->daddr = sk->__sk_common.skc_daddr;
  key->sport = sk->__sk_common.skc_num;
  key->dport = sk->__sk_common.skc_dport;
  key->protocol = IPPROTO_TCP;
  return 1;
}

int trace_tcp_sendmsg(struct pt_regs *ctx, struct sock *sk, struct msghdr *msg, size_t size) {
  struct socket_key_t key = {};

  if (!fill_key(sk, &key)) {
    return 0;
  }

  struct traffic_t zero = {};
  struct traffic_t *value = traffic.lookup_or_try_init(&key, &zero);

  if (value) {
    value->sent += size;
  }

  return 0;
}

int trace_tcp_cleanup_rbuf(struct pt_regs *ctx, struct sock *sk, int copied) {
  if (copied <= 0) {
    return 0;
  }

  struct socket_key_t key = {};

  if (!fill_key(sk, &key)) {
    return 0;
  }

  struct traffic_t zero = {};
  struct traffic_t *value = traffic.lookup_or_try_init(&key, &zero);

  if (value) {
    value->received += copied;
  }

  return 0;
}
"""

  def __init__(self):
    super(BccTrafficResolver, self).__init__()
    self._status = None
    self._bpf = None
    self._traffic = None
    self._init_backend()

  def status(self):
    return self._status

  def sample(self, connections):
    if self._status.state != 'available':
      return None

    return super(BccTrafficResolver, self).sample(connections)

  def _init_backend(self):
    if platform.system() != 'Linux':
      self._status = TrafficStatus('unavailable', 'unsupported_platform')
      return

    try:
      from bcc import BPF
    except ImportError:
      self._status = TrafficStatus('unavailable', 'bcc_missing')
      return

    try:
      self._bpf = BPF(text = self._BPF_PROGRAM)
      self._bpf.attach_kprobe(event = 'tcp_sendmsg', fn_name = 'trace_tcp_sendmsg')
      self._bpf.attach_kprobe(event = 'tcp_cleanup_rbuf', fn_name = 'trace_tcp_cleanup_rbuf')
      self._traffic = self._bpf.get_table('traffic')
      self._status = TrafficStatus('available', None)
    except Exception as exc:
      message = str(exc).lower()

      if hasattr(os, 'geteuid') and os.geteuid() != 0:
        reason = 'permission_denied'
      elif 'permission' in message or 'operation not permitted' in message:
        reason = 'permission_denied'
      else:
        reason = 'bcc_unavailable'

      self._status = TrafficStatus('unavailable', reason)
      self._bpf = None
      self._traffic = None

  def _read_totals(self):
    if self._traffic is None:
      return []

    totals = []

    for key, value in self._traffic.items():
      totals.append(SocketTraffic(_decode_bcc_key(key), int(value.sent), int(value.received)))

    return totals


def _decode_bcc_key(key):
  local_address = socket.inet_ntoa(struct.pack('I', key.saddr))
  remote_address = socket.inet_ntoa(struct.pack('I', key.daddr))
  remote_port = socket.ntohs(key.dport)

  return (local_address, int(key.sport), remote_address, int(remote_port), 'tcp')
