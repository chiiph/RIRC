from twisted.words.protocols import irc
from twisted.internet import protocol, reactor, ssl
from twisted.internet.task import LoopingCall

import time

networks = {}

from sqliter import SQLiter
from diff_consts import Diff

class RIRCProtocol(irc.IRCClient):
    def __init__(self):
        self._starting_query = {}
        self._ping_lc = LoopingCall(self._self_heartbeat)
        self._host = ""

    def _get_nickname(self):
        return self.factory.network.nick
    nickname = property(_get_nickname)

    def _add_network_msg(self, msg):
        if not isinstance(msg, list):
            msg = msg.split("\n")
        for line in msg:
            self.factory.db.add_line(time.time(),
                                     self.factory.network.name,
                                     self.factory.network.name,
                                     "@",
                                     line)

    def _self_heartbeat(self):
        print "Pinging..."
        self.sendLine("PING %s" % (self._host,))

    def created(self, when):
        self._add_network_msg(when)

    def yourHost(self, info):
        self._add_network_msg(info)

    # def myInfo(self, servername, version, umodes, cmodes):
    #     self.factory.network.servername = servername
    #     self.factory.network.umodes = umodes
    #     self.factory.network.cmodes = cmodes

    def bounce(self, info):
        print "Should bounce to:", info
        self.factory.url = info

    def signedOn(self):
        for channel in self.factory.network.channels:
            self.join(channel)
        print "Signed on as %s." % (self.nickname,)

    def privmsg(self, user, channel, msg):
        user_str = user
        channel_str = channel
        if channel == self.nickname:
            user_str = user
            channel_str = user
        self.factory.db.add_line(time.time(),
                                 self.factory.network.name,
                                 channel_str,
                                 user_str,
                                 msg)

    def noticed(self, user, channel, message):
        pass

    def modeChanged(self, user, channel, set, modes, args):
        pass

    def pong(self, user, secs):
        pass

    def kickedFrom(self, channel, kicker, message):
        pass

    def nickChanged(self, nick):
        pass

    def userQuit(self, user, quitMessage):
        channels = self.factory.db.get_channels(self.factory.network.name)
        for channel in channels:
            self.factory.db.add_line(time.time(),
                                     self.factory.network.name,
                                     channel,
                                     "-",
                                     "<== %s (%s)" % (user, quitMessage))

    def userKicked(self, kickee, channel, kicker, message):
        pass

    def action(self, user, channel, data):
        pass

    def topicUpdated(self, user, channel, newTopic):
        print "Topic:", newTopic
        self.factory.network.set_topic(channel, newTopic)
        self.factory.db.add_line(time.time(),
                                 self.factory.network.name,
                                 channel,
                                 "-",
                                 "(%s) Topic is: %s" % (user, newTopic))

    def userRenamed(self, oldname, newname):
        pass

    def receivedMOTD(self, motd):
        self._add_network_msg(motd)

    def query(self, user):
        self._starting_query[user] = True
        self.whois(user)

    def irc_unknown(self, prefix, command, params):
        self._add_network_msg("Unknown: %s :: %s" % (command, " - ".join(params)))

    def irc_PONG(self, prefix, params):
        print "Pong from %s :: %s" % (prefix, ", ".join(params))

    def irc_RPL_WHOISUSER(self, prefix, params):
        user = params[1]
        channels = self.factory.db.get_channels(self.factory.network.name)
        if user in self._starting_query.keys() and \
                self._starting_query[user] and \
                not user in channels:
            self.factory.db.add_line(time.time(),
                                     self.factory.network.name,
                                     "%s!%s@%s" % (params[1], params[2], params[3]),
                                     "-",
                                     "*** Starting query with %s ***" % (params[1]))

    def irc_RPL_NAMREPLY(self, prefix, params):
        self.factory.db.add_line(time.time(),
                                 self.factory.network.name,
                                 params[2],
                                 "-",
                                 ", ".join(params[3].split(" ")))

    def irc_JOIN(self, prefix, params):
        print "JOIN", prefix, params
        self.factory.network.set_channel_enabled(params[0])
        now = time.time()
        self.factory.db.add_line(now,
                                 self.factory.network.name,
                                 params[0],
                                 "-",
                                 "--> %s (%s)" % (prefix.split("!")[0],
                                                  prefix.split("!")[1]))
        if prefix.split("!")[0] == self.factory.network.nick:
            self.factory.db.add_diff(now, Diff.ADD_CHANNEL,
                                     self.factory.network.name,
                                     params[0])

    def irc_PART(self, prefix, params):
        print "PART", prefix, params
        msg = ""
        if prefix.split("!")[0] == self.factory.network.nick:
            self.factory.network.set_channel_enabled(params[0], False)
            msg = self.factory.network.leave_reason
        if len(params) > 1:
            msg = params[1]
        self.factory.db.add_line(time.time(),
                                 self.factory.network.name,
                                 params[0],
                                 "-",
                                 "<-- %s (%s) has left %s (%s)" % (prefix.split("!")[0],
                                                                   prefix.split("!")[1],
                                                                   params[0],
                                                                   msg))

    def yourHost(self, host):
        self._host = host.replace("Your host is ", "").split("[")[0]
        print "Starting ping loop for %s..." % (self._host,)
        self._ping_lc.start(60)

    # def irc_ERR_NICKNAMEINUSE(self, prefix, params):
    #     new_nick = self.get_next_nick()
    #     print "Nick in use!, switching to:", new_nick
    #     print "Debug: prefix: %s params: %s" % (prefix, params)
    #     self.register(new_nick)

    def close(self, channel):
        if len(channel.split("!")) == 1:
            if self.factory.network.is_channel_enabled(channel):
                self.factory.db.add_line(time.time(),
                                         self.factory.network.name,
                                         channel,
                                         "-",
                                         "** Cannot close before part **")
                return
        self.factory.db.close(self.factory.network.name, channel)

class RIRCFactory(protocol.ClientFactory):
    protocol = RIRCProtocol

    def __init__(self, network, db):
        self._network = network
        self._db = db

    def _get_db(self):
        return self._db
    db = property(_get_db)

    def _get_network_name(self):
        return self._network
    network = property(_get_network_name)

    def buildProtocol(self, addr):
        print 'Building IRC protocol...'
        p = protocol.ClientFactory.buildProtocol(self, addr)
        p.factory = self
        p.factory.network.protocol = p
        return p

    def clientConnectionLost(self, connector, reason):
        print "Lost connection (%s), reconnecting." % (reason,)
        connector.connect()

    def clientConnectionFailed(self, connector, reason):
        print "Could not connect: %s" % (reason,)

class Network(object):
    def __init__(self, db, name, use_ssl, port, url, channels = [], nicks = [], leave_reason = ""):
        object.__init__(self)

        self._name = name
        self._ssl = use_ssl
        self._port = port
        self._url = url
        self._channels = channels
        self._channel_enabled = {}
        self._nicks = nicks
        self._nick_index = 0
        self._umodes = ""
        self._cmodes = ""
        self._leave_reason = leave_reason

        self._protocol = None
        self._db = db

        self._topics = {}

        if self._ssl:
            reactor.connectSSL(url, port, RIRCFactory(self, db), ssl.ClientContextFactory())
        else:
            reactor.connectTCP(url, port, RIRCFactory(self, db))

    def _get_name(self):
        return self._name
    name = property(_get_name)

    def _get_leave_reason(self):
        return self._leave_reason
    leave_reason = property(_get_leave_reason)

    def _get_umodes(self):
        return self._umodes
    def _set_umodes(self, modes):
        self._umodes = modes
    umodes = property(fget=_get_umodes, fset=_set_umodes)

    def _get_cmodes(self):
        return self._cmodes
    def _set_cmodes(self, modes):
        self._cmodes = modes
    cmodes = property(fget=_get_cmodes, fset=_set_cmodes)

    def _get_url(self):
        return self._url
    def _set_url(self, modes):
        self._url = modes
    url = property(fget=_get_url, fset=_set_url)

    def _get_channels(self):
        return self._channels
    def _set_channels(self, modes):
        self._channels = modes
    channels = property(fget=_get_channels, fset=_set_channels)

    def set_channel_enabled(self, channel, enabled = True):
        self._channel_enabled[channel] = enabled
    def is_channel_enabled(self, channel):
        return channel in self._channel_enabled and \
            self._channel_enabled[channel]

    def _get_protocol(self):
        return self._protocol
    def _set_protocol(self, modes):
        self._protocol = modes
    protocol = property(fget=_get_protocol, fset=_set_protocol)

    def _get_nick(self):
        return self._nicks[self._nick_index]
    nick = property(fget=_get_nick)

    def get_topic(self, chan):
        if not chan in self._topics:
            return ""
        return self._topics[chan]
    def set_topic(self, chan, topic):
        self._topics[chan] = topic

    # RPCable

    def join(self, channel, key=None):
        self.protocol.join(channel, key)

    def leave(self, channel, reason=None):
        self.protocol.leave(channel, reason)

    def kick(self, channel, user, reason=None):
        self.protocol.kick(channel, user, reason)

    def topic(self, channel, topic=None):
        self.protocol.topic(channel, topic)

    def mode(self, chan, set, modes, limit=None, user=None, mask=None):
        self.protocol.mode(chan, set, modes, limit, user, mask)

    def say(self, channel, message, length=None):
        if self.is_channel_enabled(channel):
            self.protocol.say(channel, message, length)
            self._db.add_line(time.time(),
                              self.name,
                              channel,
                              "#",
                              message)
        else:
            self._db.add_line(time.time(),
                              self.name,
                              channel,
                              "-",
                              "** You parted this channel (Not delivering %s)**" % ())

    def msg(self, user, message, length=None):
        self.protocol.msg(user.split("!")[0], message, length)
        self._db.add_line(time.time(),
                          self.name,
                          user,
                          self.nick,
                          message)

    def notice(self, user, message):
        self.protocol.notice(user, message)

    def away(self, message=''):
        self.protocol.away(message)

    def back(self):
        self.protocol.back()

    def whois(self, nickname, server=None):
        self.protocol.whois(nickname, server)

    def register(self, nickname, hostname='foo', servername='bar'):
        self.protocol.register(nickname, hostname, servername)

    def setNick(self, nickname):
        self.protocol.setNick(nickname)

    def quit(self, message=''):
        self.protocol.quit(message)

    def me(self, channel, action):
        self.protocol.me(channel, action)

    def ping(self, user, text=None):
        self.protocol.ping(user, text)

    def get_next_nick(self):
        self._nick_index = (self._nick_index + 1) % len(self._nicks)
        return self._nicks[self._nick_index]

    def query(self, user):
        self.protocol.query(user)

    def close(self, channel):
        self.protocol.close(channel)

def add_network(db, name, use_ssl, port, url, channels = [], nicks = [], leave_reason = ""):
    global networks
    networks[name] = Network(db, name, use_ssl, port, url, channels, nicks, leave_reason)
