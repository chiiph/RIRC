# From http://code.activestate.com/recipes/526625-twisted-xml-rpc-server-with-basic-http-authenticat/

from __future__ import unicode_literals

import xmlrpclib
from twisted.web import xmlrpc, server, http
from twisted.internet import defer, protocol, reactor

Fault = xmlrpclib.Fault

class XmlRpcAuth(xmlrpc.XMLRPC):
    def __init__(self, user='', password=''):
        self._user = user
        self._password = password
        self._auth = (self._user !='')
        xmlrpc.XMLRPC.__init__(self, allowNone=True)

    def render(self, request):
        if self._auth:
            cleartext_token = self._user + ':' + self._password
            user = request.getUser()
            passwd = request.getPassword()

            if user=='' and passwd=='':
                request.setResponseCode(http.UNAUTHORIZED)
                return 'Authorization required!'
            else:
                token = user + ':' + passwd
                if token != cleartext_token:
                    request.setResponseCode(http.UNAUTHORIZED)
                    return 'Authorization Failed!'

        request.content.seek(0, 0)
        args, functionPath = xmlrpclib.loads(request.content.read())
        try:
            if hasattr(self, "_getFunction"):
                function = self._getFunction(functionPath)
            else:
                function = self.lookupProcedure(functionPath)
        except Fault, f:
            self._cbRender(f, request)
        else:
            request.setHeader("content-type", "text/xml")
            defer.maybeDeferred(function, *args).addErrback(
                self._ebRender
                ).addCallback(
                self._cbRender, request
                )

        return server.NOT_DONE_YET
