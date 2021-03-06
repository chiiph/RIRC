import sqlite3
import time
from os import path
from decimal import Decimal
from diff_consts import Diff

class SQLiter(object):
    def __init__(self, datadir = "datadir"):
        self._datadir = datadir
        self._conn = sqlite3.connect(path.join(datadir, "db.sqlite"))

        self._create()

    def __del__(self):
        print "Closing db..."
        self._conn.close()

    def _create(self):
        query = """create table if not exists data (
                     id integer primary key asc autoincrement,
                     date double precision,
                     network string,
                     source string,
                     channel string,
                     line string)"""

        self._conn.execute(query)
        query = """create table if not exists diffs (
                     id integer primary key asc autoincrement,
                     date double precision,
                     cmd string,
                     arg1 string,
                     arg2 string,
                     arg3 string,
                     arg4 string,
                     arg5 string)"""
        self._conn.execute(query)
        query = """create table if not exists markers (
                     id integer primary key asc autoincrement,
                     date double precision,
                     network string,
                     channel string)"""
        self._conn.execute(query)
        self._conn.commit()

    def mark(self, date, network, channel):
        query = """delete from markers where network=? and channel=?"""

        self._conn.execute(query, (network.decode("utf-8"),
                                   channel.decode("utf-8")))

        query = """insert into markers(date,network,channel) values (?,?,?)"""

        self._conn.execute(query, (date,
                                   network.decode("utf-8"),
                                   channel.decode("utf-8")))

        self._conn.commit()
        self.add_diff(time.time(), Diff.CHANGE_MARKER, network, channel, str(date))

    def get_mark(self, network, channel):
        query = """select date from markers where network=? and channel=?"""

        cur = self._conn.cursor()
        cur.execute(query, (network.decode("utf-8"),
                            channel.decode("utf-8")))
        mark = None

        for row in cur:
            mark = max(mark, Decimal(row[0]))

        return mark

    def get_diffs(self, since):
        query = """select distinct * from diffs where date > ?"""

        diffs = []
        cur = self._conn.cursor()
        cur.execute(query, (since,))
        now = Decimal(since)

        for row in cur:
            now = max(now, Decimal(row[1]))
            diffs.append(list(row))

        return diffs, now

    def get_networks(self):
        query = """select distinct network from data"""

        print "DB: Getting networks..."

        nets = []
        cur = self._conn.cursor()
        cur.execute(query)

        for row in cur:
            nets.append(row[0])

        return nets

    def get_channels(self, network):
        query = """select distinct channel from data where network=?"""

        channs = []
        cur = self._conn.cursor()
        cur.execute(query, (network,))

        for row in cur:
            channs.append(row[0])

        return channs

    def get_lines(self, network, channel, offset, count, older_than = -1):
        if older_than == -1:
            query = """select date, source, line from data where channel=? and network=?
                       order by date desc limit ? offset ?"""
        else:
            query = """select date, source, line from data where channel=? and network=?
                       and date>? order by date desc limit ? offset ?"""

        lines = []
        cur = self._conn.cursor()
        if older_than == -1:
            cur.execute(query, (channel, network, count, offset))
        else:
            cur.execute(query, (channel, network, older_than, count, offset))

        for row in cur:
            lines.append(list(row))
        return lines

    def add_line(self, date, network, channel, source, line):
        query = """insert into data(date,network,source,channel,line) values (?,?,?,?,?)"""

        self._conn.execute(query, (date,
                                   network.decode("utf-8"),
                                   source.decode("utf-8"),
                                   channel.decode("utf-8"),
                                   line.decode("utf-8")))
        self._conn.commit()
        self.add_diff(date, Diff.ADD_LINE, network, channel, source, line)

    def add_diff(self, date, cmd, arg1="", arg2="", arg3="", arg4="", arg5=""):
        query = """insert into diffs(date,cmd,arg1,arg2,arg3,arg4,arg5) values (?,?,?,?,?,?,?)"""

        self._conn.execute(query, (date,
                                   cmd,
                                   arg1.decode("utf-8"),
                                   arg2.decode("utf-8"),
                                   arg3.decode("utf-8"),
                                   arg4.decode("utf-8"),
                                   arg5.decode("utf-8")))
        self._conn.commit()

    def close(self, network, channel):
        query = """delete from data where network=? and channel=?"""

        self._conn.execute(query, (network, channel))
        self.add_diff(time.time(), Diff.CLOSE_CHANNEL, network, channel)
        self._conn.commit()
