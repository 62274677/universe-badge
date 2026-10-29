"""Stand-ins for the badge firmware's fetch and wifi modules, so ota.py imports
under CPython. Both mirror the polled state machines the firmware provides
(see badger.github.io src/lib/badge-firmware-compat.ts)."""
import sys
import types


class FakeRequest:
    """fetch.url(url).to(path): truthy once done without error; .error otherwise."""

    def __init__(self, net, url):
        self.net = net
        self.url = url
        self.error = None
        self._polls = 0
        self._done = False

    def to(self, path):
        self.path = path
        return self

    def __bool__(self):
        if self._done:
            return self.error is None
        self._polls += 1
        if self._polls < self.net.polls_per_fetch:
            return False
        self._done = True
        self.net.fetched.append(self.url)
        try:
            data = self.net.serve(self.url)
        except Exception as e:
            self.error = "HTTP 404" if isinstance(e, FileNotFoundError) else str(e)
            return False
        with open(self.path, "wb") as f:
            f.write(data)
        return True


class FakeNet:
    def __init__(self):
        self.reset()

    def reset(self):
        self.serve = lambda url: (_ for _ in ()).throw(FileNotFoundError(url))
        self.fetched = []
        self.polls_per_fetch = 2
        self.connects_after = 0  # wifi.connect() calls before it reports connected
        self.connect_calls = 0


net = FakeNet()


def _connect(*args, **kwargs):
    net.connect_calls += 1
    return net.connect_calls > net.connects_after


sys.modules["fetch"] = types.SimpleNamespace(url=lambda url, **kw: FakeRequest(net, url))
sys.modules["wifi"] = types.SimpleNamespace(connect=_connect, status=lambda: (-2, "no AP found"))
