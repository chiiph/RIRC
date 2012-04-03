from __future__ import unicode_literals

import urwid
import re

from rirc_urwid_worker import RIRCWorkerThread
from diff_consts import Diff
from datetime import datetime

class RIRCClient(object):
    def __init__(self):
        object.__init__(self)

        self._wins = []
        self._nicks = {}
        self._current_buffer = None
        self._bootstrap = True
        self._palette = [
            ('date', '', '', '', '#6d8', '#000'),
            ('nick', '', '', '', '#68d', '#000'),
            ('highlight', '','','', '#000', '#f60')
            ]
        self._cmd_edit = urwid.Edit([("I say", ">"), ""])
        self._status_line = urwid.Text("Status")
        self._footer = urwid.Pile([urwid.AttrMap(self._status_line, 'I say'),
                                   urwid.AttrMap(self._cmd_edit, 'I say')])

        self._header = urwid.Text(u"", wrap='clip')
        self._header_wrapper = urwid.AttrMap(self._header, 'header')

        self._worker = RIRCWorkerThread()
        self._buffer_channel = Channel("", "Buffers", self._worker,
                                       self._status_line,
                                       self._cmd_edit, self._footer,
                                       self._header)

        self._debug_channel = Channel("", "Debug", self._worker,
                                      self._status_line,
                                      self._cmd_edit, self._footer,
                                      self._header)


        self._screen = urwid.raw_display.Screen()
        self._screen.set_terminal_properties(256, False, True)
        self._loop = urwid.MainLoop(self._buffer_channel,
                                    self._palette,
                                    input_filter=self._input_filter,
                                    screen=self._screen)

        self._loop.set_alarm_in(0.1, self._update)

        self._show_buffers()
        self._channels = {} # key: network@channel

    def debug_run(self):
        self._worker._debug_terminal = True
        self._worker.start()
        # schedule diffs for later
        self._worker.schedule_diffs()
        # start bootstrap
        self._worker.schedule_networks()
        while True:
            try:
                self._update(None)
            except:
                self._worker.stop()
                raise

    def run(self):
        try:
            self._worker.start()
            # schedule diffs for later
            # self._worker.schedule_diffs()
            # start bootstrap
            self._worker.schedule_networks()
            self._loop.run()
        except:
            self._worker.stop()
            raise

    def _input_filter(self, input, raw):
        if unicode(input[0]) in ('page up', 'page down'):
            self._loop.widget.set_focus('body')
        else:
            self._loop.widget.set_focus('footer')

        if unicode(input[0]) == 'enter':
            try:
                cmd = self._cmd_edit.edit_text
                if cmd.startswith("/win "):
                    parts = cmd.split(" ")
                    if len(parts) == 2:
                        winid = int(parts[1])
                        self._switch_to_channel(winid)
                    else:
                        raise LookupError()
                elif cmd == "/quit":
                    self._worker.stop()
                    raise urwid.ExitMainLoop()
                elif cmd == "/wins":
                    self._show_buffers()
                elif cmd == "/debug":
                    self._show_debug()
                elif cmd == "/part":
                    self._current_buffer.part()
                elif cmd == "/close":
                    self._current_buffer.close()
                elif cmd.startswith("/join"):
                    parts = cmd.split(" ")
                    if len(parts) >= 2:
                        chann = parts[1]
                        key = None
                        if len(parts) == 3:
                            key = parts[3]
                        elif len(parts) != 2:
                            raise LookupError()
                        self._current_buffer.join(chann, key)
                    else:
                        raise LookupError()
                elif cmd.startswith("/query"):
                    parts = cmd.split(" ")
                    if len(parts) == 2:
                        user = parts[1]
                        self._current_buffer.query(user)
                    else:
                        raise LookupError()
                elif cmd.startswith("/"):
                    raise LoopupError()
                else:
                    self._current_buffer.send(cmd)
            except LookupError, e:
                self._debug(["Unknown command: %s" % (cmd,)])
            finally:
                self._cmd_edit.edit_text = ""
        #chat_box.keypress((0,400), 'page down')

        if unicode(input[0]) == 'tab':
            self._autocomplete()
            return
        return input

    def _autocomplete(self):
        pass

    def _update(self, loop, data=None):
        debugs = self._worker.get_debugs()
        if debugs:
            self._debug(debugs)
        if self._bootstrap:
            data = self._worker.get_it_all()
            if not data:
                #self._add_status("No data yet")
                if loop:
                    self._loop.set_alarm_in(0.1, self._update)
                return
            for network in data["networks"]:
                #self._add_status("Network %s" % (network,))
                for channel in data["channels"][network]:
                    #self._add_status("Channel %s" % (channel,))
                    key = network + "@" + channel
                    lines = data["lines"][key]
                    if not (network, channel) in self._wins:
                        self._wins.append((network, channel))
                    if not key in self._channels.keys():
                        nick = self._worker.get_nick(network)
                        if nick:
                            self._nicks[network] = nick
                        else:
                            self._debug(["WARNING: No nick for %s" % (network,)])
                        self._channels[key] = Channel(network, channel, self._worker,
                                                      self._status_line,
                                                      self._cmd_edit, self._footer,
                                                      self._header,
                                                      highlight = nick)
                    self._channels[key].append_new_lines(lines)

            self._bootstrap = False
            if loop:
                self._update_buffers()
        else:
            diffs = self._worker.get_diffs()
            if diffs:
                for diff in diffs:
                    # diff[0] id
                    date = diff[1]
                    cmd = diff[2]
                    if cmd == Diff.ADD_LINE:
                        network = diff[3]
                        channel = diff[4]
                        key = network + "@" + channel
                        source = diff[5]
                        msg = diff[6]
                        if not (network, channel) in self._wins:
                            self._wins.append((network, channel))
                        if not key in self._channels.keys():
                            self._channels[key] = Channel(network, channel, self._worker,
                                                          self._status_line,
                                                          self._cmd_edit, self._footer,
                                                          self._header,
                                                          self._nicks[network])
                        self._channels[key].append_new_lines([(date, source, msg)])
                    elif cmd == Diff.ADD_CHANNEL:
                        self._debug(["ADD_CHANNEL %s - %s" % (diff[3], diff[4])])
                        network = diff[3]
                        channel = diff[4]
                        if not (network, channel) in self._wins:
                            self._wins.append((network, channel))
                        self._channels[key] = Channel(network, channel, self._worker,
                                                      self._status_line,
                                                      self._cmd_edit, self._footer,
                                                      self._header,
                                                      self._nicks[network])
                    elif cmd == Diff.CLOSE_CHANNEL:
                        self._debug(["CLOSE_CHANNEL %s - %s" % (diff[3], diff[4])])
                        network = diff[3]
                        channel = diff[4]

        if loop:
            loop.set_alarm_in(0.1, self._update)

    def _debug(self, lines):
        lines = [urwid.Text(msg) for msg in lines]
        self._debug_channel.append_raw(lines)

    def _update_buffers(self):
        lines = []
        for (net, chan) in self._wins:
            lines.append(urwid.Text("%s - %s" % (net, chan)))
        self._buffer_channel.clear_and_set(lines)

    def _show_buffers(self):
        self._update_buffers()
        self._buffer_channel.switch_here(self._loop)
        self._current_buffer = self._buffer_channel

    def _show_debug(self):
        self._debug_channel.switch_here(self._loop)
        self._current_buffer = self._debug_channel

    def _switch_to_channel(self, winid):
        if winid < len(self._wins) and winid >= 0:
            net = self._wins[winid][0]
            chan = self._wins[winid][1]
            self._channels[net+"@"+chan].switch_here(self._loop)
            self._current_buffer = self._channels[net+"@"+chan]

class Channel(object):
    def __init__(self, network, name, worker, status_line, cmd_line, footer, header, highlight=None):
        object.__init__(self)
        self._network = network
        self._name = name
        self._worker = worker
        self._widget = None

        self._gui_lines = urwid.SimpleListWalker([])
        self._gui_box = urwid.ListBox(self._gui_lines)

        self._status_line = status_line
        self._cmd_line = cmd_line

        self._footer = footer
        self._header = header

        self._highlight = highlight
        if isinstance(self._highlight, str):
            self._highlight = re.compile(self._highlight)

        self._init_gui()

    def _init_gui(self):
        self._widget = urwid.Frame(body=self._gui_box,
                                   footer=self._footer,
                                   header=self._header)

    def switch_here(self, mainloop):
        self._header.set_text(self._name)
        mainloop.widget = self._widget

    def clear_and_set(self, lines):
        self._gui_lines = urwid.SimpleListWalker(lines)
        self._gui_box = urwid.ListBox(self._gui_lines)
        self._widget.set_body(self._gui_box)

    def append_raw(self, lines):
        for line in lines:
            self._gui_lines.append(line)

    def append_new_lines(self, lines):
        i = len(lines)
        while i > 0:
            i -= 1
            line = "%s" % (lines[i][2],)
            nick = "<%s> " % (lines[i][1].split("!")[0],)
            if nick != "<-> " and self._highlight and \
                    self._highlight.match(lines[i][2]):
                line = ('highlight', line)
            self._gui_lines.append(urwid.Text(["%s - " % (datetime.fromtimestamp(lines[i][0])\
                                                              .strftime("%d/%m/%y %H:%M:%S"),),
                                               ('nick', nick),
                                               line]))

    def send(self, msg):
        self._worker.send(self._network, self._name, msg)

    def join(self, channel, key):
        self._worker.join_channel(self._network, channel, key)

    def query(self, user):
        self._worker.query_user(self._network, user)

    def part(self):
        self._worker.part_channel(self._network, self._name)

    def close(self):
        self._worker.close_channel(self._network, self._name)

if __name__ == "__main__":
    client = RIRCClient()
    client.debug_run()
