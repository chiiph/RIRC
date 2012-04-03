import threading
import simplejson as json
import urwid
import xmlrpclib
import copy
import time
import Queue
from M2Crypto import m2xmlrpclib, SSL
from decimal import Decimal

class RIRCWorkerThread(threading.Thread):
    IDLE = -1
    INIT = 0
    SEND = 1
    NETWORKS = 2
    CHANNELS = 3
    LINES = 4
    DIFFS = 5
    JOIN = 6
    QUERY = 7
    def __init__(self, debug = False):
        threading.Thread.__init__(self)

        # stages stack
        self._stages = []
        self._stages.append((self.IDLE,None))
        self._ready = False

        self._read_lock = threading.Lock()
        self._scheduler_lock = threading.Lock()
        self._debug_lock = threading.Lock()
        self._send_lock = threading.Lock()

        self._msg_queue = Queue.Queue()
        self._networks = []
        self._channels = {}
        self._lines = {}
        self._older_line = {}
        self._last_time = 0
        self._diffs = {}
        self._debug_queue = []

        self._debug_terminal = debug

        context = SSL.Context()
        context.load_verify_info(cafile="/home/chiiph/.config/rirc/rirc.pem")
        context.set_verify(SSL.verify_fail_if_no_peer_cert, 0)
        proxy = xmlrpclib.ServerProxy("https://chiiph:supersecret@tldr.com.ar:4343/", allow_none = True,
                                      transport=m2xmlrpclib.SSL_Transport(ssl_context=context))
        self._proxy = proxy
        self._stop = threading.Event()

    def _print(self, msg):
        self._debug(msg)
        if self._debug_terminal:
            print msg

    def _debug(self, msg):
        self._debug_lock.acquire(True)
        self._debug_queue.append(msg)
        self._debug_lock.release()

    def _reset(self):
        self._networks = []
        self._channels = {}
        self._lines = {}
        self._ready = False

    def get_debugs(self):
        debugs = None
        if self._debug_lock.acquire(False):
            debugs = copy.deepcopy(self._debug_queue)
            self._debug_queue = []
            self._debug_lock.release()
        return debugs

    def get_it_all(self):
        obj = None
        if self._read_lock.acquire(False):
            if self._ready:
                net = copy.deepcopy(self._networks)
                channs = copy.deepcopy(self._channels)
                lines = copy.deepcopy(self._lines)
                self._reset()
                obj = {"networks":net,
                       "channels":channs,
                       "lines":lines}
            self._read_lock.release()
        return obj

    def get_diffs(self):
        obj = None
        if self._read_lock.acquire(False):
            obj = copy.deepcopy(self._diffs)
            self._diffs = {}
            self._read_lock.release()
        return obj

    def get_networks(self):
        obj = None
        if self._read_lock.acquire(False):
            obj = copy.deepcopy(self._networks)
            self._read_lock.release()
        return obj

    def get_channels(self, network):
        obj = None
        if self._read_lock.acquire(False):
            if network in self._channels.keys():
                obj = copy.deepcopy(self._channels[network])
            self._read_lock.release()
        return obj

    def get_lines(self, network, channel):
        obj = None
        if self._read_lock.acquire(False):
            key = network + "@" + channel
            if key in self._lines.keys():
                obj = copy.deepcopy(self._lines[key])
            self._read_lock.release()
        return obj

    def stop(self):
        self._stop.set()

    def stopped(self):
        return self._stop.is_set()

    def _schedule(self, task, data=None):
        self._scheduler_lock.acquire(True)
        self._stages.append((task, data))
        self._scheduler_lock.release()

    def _get_schedule(self):
        self._scheduler_lock.acquire(True)
        if len(self._stages) == 0:
            task = (self.DIFFS, None)
        else:
            task = self._stages.pop()
        self._scheduler_lock.release()
        return task

    def schedule_networks(self):
        self._schedule(self.NETWORKS)

    def schedule_channels(self, network):
        self._schedule(self.CHANNELS, network)

    def schedule_lines(self, network, channels):
        self._schedule(self.LINES, (network, channels))

    def schedule_diffs(self):
        self._schedule(self.DIFFS)

    def schedule_idle(self, time):
        self._schedule(self.IDLE, time)

    def send(self, network, channel, msg):
        self._scheduler_lock.acquire(True)
        # Give it more priority to sending
        if (self.SEND, None) in self._stages:
            self._stages.remove((self.SEND, None))
        self._stages.append((self.SEND, None))
        self._debug("Scheduling send %s - %s - %s" % (network, channel, msg))
        self._debug("Queue is: %s" % (str(self._stages)))
        self._send_lock.acquire(True)
        self._msg_queue.put((network, channel, msg))
        self._send_lock.release()
        self._scheduler_lock.release()

    def join_channel(self, network, channel, key=None):
        self._schedule(self.JOIN, (network, channel, key))
        self._debug("Scheduling join %s - %s" % (network, channel))

    def join_channel(self, network, user):
        self._schedule(self.QUERY, (network, user))
        self._debug("Scheduling query %s - %s" % (network, user))

    def run(self):
        while True:
            self._debug("** Starting loop")
            if self.stopped():
                print "Stopped..."
                break
            self._read_lock.acquire(True)

            stage, data = self._get_schedule()
            self._debug("Queue is: %s" % (str(self._stages)))
            self._debug("Doing: %s" % (str(tuple([stage, data]))))
            if stage == self.SEND:
                self._send_lock.acquire(True)
                try:
                    net_msg, chan_msg, msg = self._msg_queue.get()
                    self._debug("Sending %s - %s - %s" % (net_msg, chan_msg, msg))
                    if len(chan_msg.split("!")):
                        self._proxy.msg(net_msg, chan_msg, msg)
                    else:
                        self._proxy.say(net_msg, chan_msg, msg)
                except Queue.Empty, e:
                    pass
                finally:
                    if not self._msg_queue.empty():
                        self._schedule(self.SEND)
                    self._send_lock.release()
            elif stage == self.NETWORKS:
                self._print("Stage is networks")
                self._networks = json.loads(self._proxy.get_networks())["networks"]
                self._print(self._networks)
                self.schedule_channels(self._networks)
            elif stage == self.CHANNELS:
                self._print("Stage is channels")
                for network in data:
                    self._channels[network] = json.loads(self._proxy.get_channels(network))["channels"]
                    self._print(self._channels[network])
                    self.schedule_lines(network, self._channels[network])
            elif stage == self.LINES:
                self._print("Stage is lines")
                network, channels = data
                for channel in channels:
                    self._print(channel)
                    key = network + "@" + channel
                    if not key in self._older_line.keys():
                        self._older_line[key] = -1
                    if not key in self._lines.keys():
                        self._lines[key] = []
                    self._lines[key] = self._lines[key] + json.loads(self._proxy.get_lines(network,
                                                                                           channel,
                                                                                           0, 400,
                                                                                           float(self._older_line[key])),
                                                                     parse_float=self._parse_timestamp)["lines"]
                    if len(self._lines[key]) > 0:
                        self._older_line[key] = max(self._older_line[key],
                                                    max(self._lines[key][0][0],
                                                        self._lines[key][-1][0]))

                self._last_time = max(self._older_line.values())
                self._ready = True
            elif stage == self.DIFFS:
                res = self._proxy.get_diffs(float(self._last_time))
                diffs = json.loads(res, parse_float=self._parse_timestamp)
                self._last_time = diffs["timestamp"]
                self._diffs = diffs["changes"]
            elif stage == self.IDLE:
                if data:
                    time.sleep(data)
            elif stage == self.JOIN:
                network, channel, key = data
                self._proxy.join(network, channel, key)
            elif stage == self.QUERY:
                network, user = data
                self._proxy.query(network, user)
            self._read_lock.release()
            time.sleep(0.1)

    def _parse_timestamp(self, val):
        return Decimal(val)