from twisted.web import xmlrpc, server, http
from twisted.words.protocols import irc
from twisted.internet import protocol, defer, reactor, ssl

import sys

from ConfigParser import ConfigParser
from os import path
import simplejson as json

from xmlrpcauth import XmlRpcAuth
from sqliter import SQLiter
from network import add_network, networks

class RIRC(XmlRpcAuth):
    def __init__(self, datadir = "datadir", user = "", password = ""):
        XmlRpcAuth.__init__(self, user, password)

        self._leave_reason = ""
        self._datadir = datadir
        self._db = SQLiter(self._datadir)
        self._port = 0
        self.loadConfig(path.join(self._datadir,
                                  "rirc.cfg"))

    def _get_port(self):
        return self._port
    port = property(_get_port)

    def loadConfig(self, path):
        self.config = ConfigParser()
        self.config.read([path])

        for section in self.config.sections():
            if section == "General":
                self._port = self.config.getint(section, "ServePort")
                self._auth = self.config.getboolean(section, "UseAuth")
                if(self._auth):
                    self._user = self.config.get(section, "User")
                    self._password = self.config.get(section, "Password")
                self._leave_reason = self.config.get(section, "LeaveReason")
                continue

            add_network(self._db,
                        name     = section,
                        use_ssl  = self.config.getboolean(section, "SSL"),
                        url      = self.config.get(section, "URL"),
                        port     = self.config.getint(section, "Port"),
                        channels = self.config.get(section, "AutoJoin").split(","),
                        nicks    = self.config.get(section, "Nicks").split(","),
                        leave_reason = self._leave_reason)

    def xmlrpc_join(self, network, channel, key=None):
        global networks
        if network in networks.keys():
           networks[network].join(channel, key)

    def xmlrpc_leave(self, network, channel, reason=None):
        global networks
        if network in networks.keys():
            networks[network].leave(channel, reason)

    def xmlrpc_close(self, network, channel):
        global networks
        if network in networks.keys():
            networks[network].close(channel)

    def xmlrpc_kick(self, network, channel, user, reason=None):
        global networks
        if network in networks.keys():
            networks[network].kick(channel, user, reason)

    def xmlrpc_topic(self, network, channel, topic=None):
        global networks
        if network in networks.keys():
            networks[network].topic(channel, topic)

    def xmlrpc_get_topic(self, network, channel):
        global networks
        if network in networks.keys():
            return networks[network].get_topic(channel)

    def xmlrpc_mode(self, network, chan, set, modes, limit=None, user=None, mask=None):
        global networks
        if network in networks.keys():
            networks[network].mode(chan, set, modes, limit, user, mask)

    def xmlrpc_say(self, network, channel, message, length=None):
        global networks
        if network in networks.keys():
            networks[network].say(channel, message, length)

    def xmlrpc_msg(self, network, user, message, length=None):
        global networks
        if network in networks.keys():
            networks[network].msg(user, message, length)

    def xmlrpc_notice(self, network, user, message):
        global networks
        if network in networks.keys():
            networks[network].notice(user, message)

    def xmlrpc_away(self, network, message=''):
        global networks
        if network in networks.keys():
            networks[network].away(message)

    def xmlrpc_back(self):
        global networks
        if network in networks.keys():
            networks[network].back()

    def xmlrpc_whois(self, network, nickname, server=None):
        global networks
        if network in networks.keys():
            networks[network].whois(nickname, server)

    def xmlrpc_query(self, network, nickname):
        global networks
        if network in networks.keys():
            networks[network].query(nickname)

    def xmlrpc_register(self, network, nickname, hostname='foo', servername='bar'):
        global networks
        if network in networks.keys():
            networks[network].register(nickname, hostname, servername)

    def xmlrpc_setNick(self, network, nickname):
        global networks
        if network in networks.keys():
            networks[network].setNick(nickname)

    def xmlrpc_quit(self, network, message=''):
        global networks
        if network in networks.keys():
            networks[network].quit(message)

    def xmlrpc_me(self, network, channel, action):
        global networks
        if network in networks.keys():
            networks[network].me(channel, action)

    def xmlrpc_ping(self, network, user, text=None):
        global networks
        if network in networks.keys():
            if len(user) == 0:
                user = networks[network].nick
            networks[network].ping(user, text)

    def xmlrpc_get_networks(self):
        return json.dumps({"networks": self._db.get_networks()},
                          indent=' ')

    def xmlrpc_get_channels(self, network):
        return json.dumps({"network": network,
                           "channels": self._db.get_channels(network)},
                          indent=' ')

    def xmlrpc_get_lines(self, network, channel, offset, count, older_than = -1):
        return json.dumps({"network": network,
                           "channel": channel,
                           "lines": self._db.get_lines(network, channel,
                                                       offset, count,
                                                       older_than)},
                          indent=' ')

    def xmlrpc_nick(self, network):
        global networks
        if network in networks.keys():
            return networks[network].nick

    def xmlrpc_get_diffs(self, since):
        diffs, now = self._db.get_diffs(since)
        print diffs, now
        return json.dumps({"changes": diffs,
                           "timestamp": now})

if __name__ == "__main__":
    datadir = sys.argv[1]
    cert = path.join(datadir, "rirc.pem")
    priv = path.join(datadir, "rirc_priv.pem")
    s = RIRC(datadir=datadir)
    sslContext = ssl.DefaultOpenSSLContextFactory(priv, cert)
    reactor.listenSSL(s.port, server.Site(s), sslContext)
    reactor.run()
