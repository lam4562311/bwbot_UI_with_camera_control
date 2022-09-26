"""asyncio-based networking facilities for implementing WS-Discovery daemons; requires Python 3.7+"""

import asyncio
import logging
import random
import time
import uuid
import socket
import struct

from collections.abc import Awaitable

from .udp import UDPMessage
from .actions import *
from .uri import URI
from .util import _getNetworkAddrs
from .message import createSOAPMessage, parseSOAPMessage
from .service import Service
from .envelope import SoapEnvelope
from .threaded import NetworkingThread as NT


# hack for now... we need some refactoring here
_createMulticastInSocket = NT._createMulticastInSocket
_createMulticastOutSocket = NT._createMulticastOutSocket
_makeMreq = NT._makeMreq


logger = logging.getLogger("asyncrun")
logging.basicConfig()

BUFFER_SIZE = 0xffff
NETWORK_ADDRESSES_CHECK_TIMEOUT = 5
MULTICAST_PORT = 3702
MULTICAST_IPV4_ADDRESS = "239.255.255.250"


class SubscribersContainer(type):
    "annotate classes with their own subscriber list"
    def __new__(cls, name, bases, dct):
        EvtClass = super().__new__(cls, name, bases, dct)
        EvtClass.subscribers = []
        return EvtClass

class Event(metaclass=SubscribersContainer):
    "base class that gives each subclass its own subscriber list"

    def __init__(self, *args, **kwargs):
        self.args = args
        self.__dict__.update(kwargs)

    @classmethod
    def subscribe(cls, subscriber):
        cls.subscribers.append(subscriber)

    @classmethod
    def unsubscribe(cls, subscriber):
        cls.subscribers.remove(subscriber)

    def notify(self, value=None):
        for subscriber in self.__class__.subscribers:
            subscriber(value or self)


class AddressAddedEvent(Event):
    "local system address was added"
    address = None


class AddressRemovedEvent(Event):
    "local system address was removed"
    address = None


class MessageReceivedEvent(Event):
    "WS-Discovery message was received"
    message = None
    source = None


class ProbeMatchReceivedEvent(Event):
    "Probe match received"
    message = None
    source = None


class WSDicoveryProtocol(asyncio.DatagramProtocol):
    
    logger = logging.getLogger(__qualname__)
    logger.setLevel(logging.DEBUG)

    def __init__(self):
        self._addressmonitor = AddressMonitor()
        self._knownMessageIds = set()
        self._iidMap = {}

    def connection_made(self, transport):
        self.transport = transport

    def message_received(self, env: SoapEnvelope, addr):

        # manage set of known message identifiers
        mid = env.getMessageId()
        if mid in self._knownMessageIds:
            return
        else:
            self._knownMessageIds.add(mid)

        # manage mapping of message numbers by address-instanceid keys
        iid = env.getInstanceId()
        if len(iid) > 0 and int(iid) >= 0:
            mnum = env.getMessageNumber()
            key = addr[0] + ":" + str(addr[1]) + ":" + str(iid)
            if mid is not None and len(mid) > 0:
                key = key + ":" + mid
            if key not in self._iidMap:
                self._iidMap[key] = iid
            else:
                tmnum = self._iidMap[key]
                if mnum > tmnum:
                    self._iidMap[key] = mnum
                else:
                    return

        MessageReceivedEvent(message=env, source=addr).notify()

    def datagram_received(self, data, addr):
        "deserialize message & notify subscribers"
        env = parseSOAPMessage(data, addr[0])

        if env is None: # fault or failed to parse
            return

        self.message_received(env, addr)


    def error_received(self, exc):
        "UDP networking issue was detected"
        raise exc

    async def send_message(self, msg: UDPMessage):
        "send the UDPMessage according to the repeat & delay policy"
        data = createSOAPMessage(msg.getEnv()).encode("UTF-8")
        while not msg.isFinished():
            self.transport.sendto(data, (msg.getAddr(), msg.getPort()))
            msg.refresh()
            await asyncio.sleep(msg._t / 1000)

    
class Stoppable:
    "Stoppable daemon mixin"

    def __init__(self):
        self._stopping = asyncio.Event()
        self._daemon = True

    def stop(self):
        "Schedule stopping the daemon"
        self._stopping.set()


class AddressMonitor(Stoppable):
    "trigger address change callbacks when local service addresses change"

    def __init__(self):
        self.addrs = set(_getNetworkAddrs())
        super().__init__()

    async def updateAddrs(self):
        addrs = set(_getNetworkAddrs())
        disappeared = self.addrs.difference(addrs)
        added = addrs.difference(self.addrs)

        for oldaddr in disappeared:
            AddressRemovedEvent().notify(oldaddr)

        for newaddr in added:
            AddressAddedEvent().notify(newaddr)

        self.addrs = addrs
        
    async def run(self):
        while not self._stopping.is_set():
            await self.updateAddrs()
            await asyncio.sleep(NETWORK_ADDRESSES_CHECK_TIMEOUT)


class Networking:
    def __init__(self):
        self._knownMessageIds = set()
        self._iidMap = {}
        self._quitEvent = asyncio.Event()
        self._ttl = 1

        AddressAddedEvent.subscribe(self.addSourceAddr)
        AddressRemovedEvent.subscribe(self.removeSourceAddr)
        MessageReceivedEvent.subscribe(self.handleMessage)

    def addSourceAddr(self, addr):
        """None means 'system default'"""
        try:
            self._multiInSocket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, _makeMreq(addr))
        except socket.error:  # if 1 interface has more than 1 address, exception is raised for the second
            pass

        sock = _createMulticastOutSocket(addr, self._ttl)
        self._multiOutUniInSockets[addr] = sock


    def removeSourceAddr(self, addr):
        try:
            self._multiInSocket.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, _makeMreq(addr))
        except socket.error:  # see comments for setsockopt(.., socket.IP_ADD_MEMBERSHIP..
            pass

        sock = self._multiOutUniInSockets[addr]
        self._selector.unregister(sock)
        sock.close()
        del self._multiOutUniInSockets[addr]


    def send_message(self, msg):
        data = createSOAPMessage(msg.getEnv()).encode("UTF-8")

        if msg.msgType() == UDPMessage.UNICAST:
            self._uniOutSocket.sendto(data, (msg.getAddr(), msg.getPort()))
        else:
            for sock in list(self._multiOutUniInSockets.values()):
                sock.sendto(data, (msg.getAddr(), msg.getPort()))


    async def start(self):

        self._uniOutSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        tp, proto = await loop.create_datagram_endpoint(WSDicoveryProtocol, sock=self._uniOutSocket)
        self._uniOutTransport = tp
        self._uniOutProtocol = proto

        self._multiInSocket = self._createMulticastInSocket()
        self._multiInEndpoint = await loop.create_datagram_endpoint(WSDicoveryProtocol, sock=self._multiInSocket)

        self._selector.register(self._multiInSocket, selectors.EVENT_WRITE | selectors.EVENT_READ)

        self._multiOutUniInSockets = {}

        try:
            await self._quitEvent.wait()
        except asyncio.CancelledError:
            self._uniOutTransport.close()


    async def sendUnicastMessage(self, env, addr, port, initialDelay=0):
        "handle unicast message sending"
        msg = UDPMessage(env, addr, port, UDPMessage.UNICAST, initialDelay)
        self._knownMessageIds.add(env.getMessageId())
        sender = self._uniOutProtocol.send_message(msg)
        asyncio.create_task(sender)

    async def sendMulticastMessage(self, env, initialDelay=0):
        "handle multicast message sending"
        msg = UDPMessage(env, MULTICAST_IPV4_ADDRESS, MULTICAST_PORT, UDPMessage.MULTICAST, initialDelay)
        self._knownMessageIds.add(env.getMessageId())


