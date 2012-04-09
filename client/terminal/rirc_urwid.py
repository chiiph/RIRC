import urwid
import re
import time

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
            ('highlight', '','','', '#000', '#f60'),
            ('highlight_notification', '','','', '#f60', '#000'),
            ('status_line', '','','','#ccc', '#000'),
            ]
        self._cmd_edit = urwid.Edit("")
        self._status_line = urwid.Padding(urwid.Text("Status"))
        self._footer = urwid.Pile([urwid.AttrMap(self._status_line, 'status_line'),
                                   self._cmd_edit])

        self._header = urwid.Padding(urwid.Text(""))
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
                    self._current_buffer.mark()
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
                    raise LookupError()
                else:
                    self._current_buffer.send(cmd)
            except LookupError, e:
                self._debug(["Unknown command: %s" % (cmd,)])
            finally:
                self._cmd_edit.edit_text = ""

        if unicode(input[0]) == 'tab':
            self._autocomplete()
            return
        return input

    def _autocomplete(self):
        pass

    def _update(self, loop, data=None):
        self._update_buffers()
        debugs = self._worker.get_debugs()
        if debugs:
            self._debug(debugs)
        if self._bootstrap:
            data = self._worker.get_it_all()
            if not data:
                if loop:
                    self._loop.set_alarm_in(0.1, self._update)
                return
            for network in data["networks"]:
                for channel in data["channels"][network]:
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
                    marker = self._worker.get_marker(network, channel)
                    self._channels[key].append_new_lines(lines, marker, False)

            self._bootstrap = False
            if loop:
                self._update_buffers()
        else:
            for network, channel in self._wins:
                key = network + "@" + channel
                if not self._channels[key].marked:
                    marker = self._worker.get_marker(network, channel)
                    if marker:
                        self._channels[key].insert_marker(marker, True)
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
                        if not network in self._nicks:
                            nick = self._worker.get_nick(network)
                            if nick:
                                self._nicks[network] = nick
                        if not key in self._channels.keys():
                            self._channels[key] = Channel(network, channel, self._worker,
                                                          self._status_line,
                                                          self._cmd_edit, self._footer,
                                                          self._header,
                                                          self._nicks[network])
                        else:
                            if network in self._nicks:
                                self._channels[key].highlight = self._nicks[network]

                        marker = self._worker.get_marker(network, channel)
                        self._channels[key].append_new_lines([(date, source, msg)],
                                                             notify=self._current_buffer != \
                                                                 self._channels[key])
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
                    elif cmd == Diff.CHANGE_MARKER:
                        self._debug(["CHANGE_MARKER %s - %s" % (diff[3], diff[4])])
                        network = diff[3]
                        channel = diff[4]
                        marker = diff[5]
                        self._channels[network+"@"+channel].insert_marker(marker)

        if loop:
            loop.set_alarm_in(0.1, self._update)
        self._update_status_line()

    def _debug(self, lines):
        lines = [urwid.Text(msg) for msg in lines]
        self._debug_channel.append_raw(lines)

    def _update_buffers(self):
        lines = []
        index = 0
        for (net, chan) in self._wins:
            key = net+"@"+chan
            pending = self._channels[key].pending_msgs
            line = "(%d) %s - %s (%d)" % (index,
                                          net, chan,
                                          pending)
            if self._channels[key].has_notifications and \
                    self._channels[key].notification_type == Channel.Highlight:
                line = ('highlight_notification', line)
            lines.append(urwid.Text(line))
            index += 1
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
            self._current_buffer.mark()
            self._channels[net+"@"+chan].switch_here(self._loop)
            self._current_buffer = self._channels[net+"@"+chan]

    def _update_status_line(self):
        status = ["Activity: "]
        first = True
        index = 0
        for network, channel in self._wins:
            key = network + "@" + channel
            if self._channels[key].has_notifications:
                if not first:
                    status += ", "
                notification_type = self._channels[key].notification_type
                if notification_type == Channel.Highlight:
                    status.append(('highlight_notification', "(%d)%s: [%d]" % \
                                      (index,
                                       self._channels[key].name.split("!")[0],
                                       self._channels[key].pending_msgs)))
                else:
                    status.append("%d: %d" % (index, self._channels[key].pending_msgs))
                if first:
                    first = False
            index += 1
        if first: # no notifications
            status = ['No activity']
        self._status_line.base_widget.set_text(('status_line', status))

class Channel(object):
    Normal = 0
    Highlight = 1
    def __init__(self, network, name, worker, status_line, cmd_line, footer, header, highlight=None):
        object.__init__(self)
        self._network = network
        self._name = name
        self._worker = worker
        self._widget = None
        self._internal = (len(network) == 0)
        self._raw_lines = []

        self._gui_lines = urwid.SimpleListWalker([])
        self._gui_box = urwid.ListBox(self._gui_lines)

        self._status_line = status_line
        self._cmd_line = cmd_line

        self._footer = footer
        self._header = header
        self._marker = None
        self._marker_date = 0

        self._highlight = highlight
        if isinstance(self._highlight, str):
            self._highlight = re.compile(self._highlight)

        self._has_notifications = False
        self._notification_type = Channel.Normal
        self._pending_msgs = 0

        self._init_gui()

    def _get_name(self):
        return self._name
    name = property(_get_name)

    def _is_marked(self):
        return not (self._marker is None)
    marked = property(_is_marked)

    def _is_internal(self):
        return self._internal
    internal = property(_is_internal)

    def _get_has_notifications(self):
        return self._has_notifications
    has_notifications = property(_get_has_notifications)

    def _get_notification_type(self):
        return self._notification_type
    notification_type = property(_get_notification_type)

    def _get_pending_msgs(self):
        return self._pending_msgs
    pending_msgs = property(_get_pending_msgs)

    def _get_highlight(self):
        return self._highlight
    def _set_highlight(self, val):
        self._highlight = val
        if isinstance(self._highlight, str):
            self._highlight = re.compile(self._highlight)
    highlight = property(fget=_get_highlight, fset=_set_highlight)

    def _init_gui(self):
        self._widget = urwid.Frame(body=self._gui_box,
                                   footer=self._footer,
                                   header=self._header)

    def scroll_down(self):
        self._gui_lines.set_focus(len(self._gui_lines)-1)

    def switch_here(self, mainloop):
        header_str = "%s - %s" % (self._network, self._name)
        if len(self._network) == 0:
            header_str = self._name
        self._header.base_widget.set_text(('highlight_notification',
                                           header_str))
        mainloop.widget = self._widget
        self._has_notifications = False
        self._pending_msgs = 0

    def clear_and_set(self, lines):
        self._gui_lines = urwid.SimpleListWalker(lines)
        self._gui_box = urwid.ListBox(self._gui_lines)
        self._widget.set_body(self._gui_box)

    def append_raw(self, lines):
        for line in lines:
            self._gui_lines.append(line)

    def append_new_lines(self, lines, marker=None, notify=True):
        i = len(lines)
        while i > 0:
            i -= 1
            line = "%s" % (lines[i][2],)
            nick = "<%s> " % (lines[i][1].split("!")[0],)
            if nick != "<-> " and self._highlight and \
                    self._highlight.match(lines[i][2]):
                line = ('highlight', line)
                if notify:
                    self._has_notifications = True
                    self._notification_type = Channel.Highlight
            self._gui_lines.append(urwid.Text([('date', "%s - " % (datetime.fromtimestamp(lines[i][0])\
                                                                       .strftime("%d/%m/%y %H:%M:%S"),)),
                                               ('nick', nick),
                                               line]))
            self._raw_lines.append((lines[i][0], lines[i][1], lines[i][2]))

        if notify:
            self._has_notifications = len(lines)>0
            if self._notification_type == Channel.Normal and \
                    not self.name.startswith("#"):
                self._notification_type = Channel.Highlight
        if self.has_notifications:
            self._pending_msgs += len(lines)
        self.scroll_down()

    def insert_marker(self, marker, notify=False):
        if self._marker: # if there already is a marker, remove it
            self._gui_lines.remove(self._marker)
            self._marker = None
        self._marker = urwid.Divider("#")
        self._marker_date = marker
        index = 0
        start_notify = False
        for line in self._raw_lines:
            if not start_notify:
                index += 1
            else:
                if line[1] != "<-> " and self._highlight and \
                        self._highlight.match(line[2]):
                    line = ('highlight', line)
                    if notify:
                        self._has_notifications = True
                        self._notification_type = Channel.Highlight
                self._pending_msgs += 1
            if line[0] > marker:
                start_notify = True
        if notify:
            self._has_notifications = self._pending_msgs > 0
            if self._notification_type == Channel.Normal and \
                    not self.name.startswith("#"):
                self._notification_type = Channel.Highlight
        else:
            self._has_notifications = False
            self._pending_msgs = 0
            self._notification_type = Channel.Normal
        self._gui_lines.insert(index, self._marker)

    def send(self, msg):
        if len(msg.strip()) == 0:
            return
        self._worker.send(self._network, self._name, msg.decode('utf-8').encode('utf-8'))

    def join(self, channel, key):
        self._worker.join_channel(self._network, channel, key)

    def query(self, user):
        self._worker.query_user(self._network, user)

    def part(self):
        self._worker.part_channel(self._network, self._name)

    def close(self):
        self._worker.close_channel(self._network, self._name)

    def mark(self):
        if self.internal:
            return
        self._worker.mark(time.time(), self._network, self._name)

if __name__ == "__main__":
    client = RIRCClient()
    client.run()
