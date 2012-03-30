import sqlite3
from os import path

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
                     date string,
                     network string,
                     source string,
                     channel string,
                     line string)"""

        self._conn.execute(query)
        self._conn.commit()

    def get_networks(self):
        query = """select distinct network from data"""

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

        self._conn.execute(query, (date, network, source, channel, line))
        self._conn.commit()

    def close(self, network, channel):
        query = """delete from data where network=? and channel=?"""

        self._conn.execute(query, (network, channel))
        self._conn.commit()
