"""
Loaded by run_ci.py (via PYTHONPATH) into every suite it runs.

It refuses every connection that is not to this machine and every DNS lookup,
and writes what was attempted to $CI_NET_LOG. A suite listed as offline that
reaches for the network then fails the gate by name, instead of passing on a
good day and failing on a day Yahoo is slow.

VALIDATION.md once said these suites' network calls were monkeypatched. For one
of the three it was not true, and nothing enforced it. This enforces it.
"""
import os
import socket

_LOG = os.environ.get("CI_NET_LOG")
_LOCAL = ("127.0.0.1", "::1", "localhost", "0.0.0.0")


def _log(line):
    if _LOG:
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def _host(addr):
    return addr[0] if isinstance(addr, tuple) and addr else str(addr)


def _is_local(sock, addr):
    return sock.family == getattr(socket, "AF_UNIX", -1) or _host(addr) in _LOCAL


_orig_connect = socket.socket.connect
_orig_connect_ex = socket.socket.connect_ex
_orig_getaddrinfo = socket.getaddrinfo


def _connect(self, addr, *a, **k):
    if _is_local(self, addr):
        return _orig_connect(self, addr, *a, **k)
    _log("net:" + _host(addr))
    raise OSError("network blocked by the CI gate: " + _host(addr))


def _connect_ex(self, addr, *a, **k):
    if _is_local(self, addr):
        return _orig_connect_ex(self, addr, *a, **k)
    _log("net:" + _host(addr))
    return 111                                   # ECONNREFUSED


def _getaddrinfo(host, *a, **k):
    if host is None or host in _LOCAL:
        return _orig_getaddrinfo(host, *a, **k)
    _log("dns:" + str(host))
    raise socket.gaierror("DNS blocked by the CI gate: " + str(host))


class _CurlGuard:
    """
    yfinance downloads through curl_cffi, which is libcurl in C and never calls
    Python's socket module, so the patches above cannot see it. With only those
    in place, yf.download() fetched five real days of RELIANCE while this file
    logged nothing. Every synchronous curl_cffi request goes through
    Curl.perform, so that is wrapped the moment curl_cffi.curl is imported.
    (psycopg2 is also C and also bypasses sockets; run_ci.py removes
    DATABASE_URL so there is no address for it to reach.)
    """

    def find_spec(self, name, path=None, target=None):
        if name != "curl_cffi.curl":
            return None
        import importlib.util
        import sys
        sys.meta_path.remove(self)
        try:
            spec = importlib.util.find_spec(name)
        finally:
            sys.meta_path.insert(0, self)
        if spec is None or spec.loader is None:
            return spec
        original = spec.loader.exec_module

        def exec_module(module):
            original(module)
            curl = getattr(module, "Curl", None)
            if curl is None:
                return
            err = getattr(module, "CurlError", OSError)

            def perform(self, *a, **k):
                _log("net:curl_cffi")
                raise err("network blocked by the CI gate (curl_cffi)")

            curl.perform = perform

        spec.loader.exec_module = exec_module
        return spec


if _LOG:                                         # inert unless run_ci.py set it up
    import sys as _sys
    socket.socket.connect = _connect
    socket.socket.connect_ex = _connect_ex
    socket.getaddrinfo = _getaddrinfo
    _sys.meta_path.insert(0, _CurlGuard())
