#!/usr/bin/env python3
import json
import re
import socket
import struct

import rospy

PREFIX = struct.Struct('!II')
MAX_HEADER = 1024 * 1024
TOPIC_RE = re.compile(r'^/[A-Za-z][A-Za-z0-9_/]*$')


def settings():
    topics = rospy.get_param('~topics', [])
    queue_size = rospy.get_param('~queue_size', 10)
    max_bytes = rospy.get_param('~max_message_bytes', 33554432)
    if (not isinstance(topics, list) or not topics or
            any(not isinstance(t, str) or not TOPIC_RE.fullmatch(t) or '//' in t or t.endswith('/') for t in topics) or
            len(topics) != len(set(topics))):
        raise ValueError('topics must be a nonempty list of unique absolute ROS topic names')
    if type(queue_size) is not int or queue_size < 1 or type(max_bytes) is not int or not 1 <= max_bytes <= 0xffffffff:
        raise ValueError('queue_size and max_message_bytes must be positive integers')
    return topics, queue_size, max_bytes


def encode(header, payload, max_bytes):
    meta = json.dumps(header, ensure_ascii=True, separators=(',', ':')).encode('utf-8')
    if len(meta) > MAX_HEADER or len(payload) > max_bytes:
        raise ValueError('frame exceeds configured size limit')
    return PREFIX.pack(len(meta), len(payload)) + meta + payload


def read_exact(sock, size):
    chunks = bytearray()
    while len(chunks) < size:
        try:
            chunk = sock.recv(min(size - len(chunks), 65536))
        except socket.timeout:
            if rospy.is_shutdown():
                raise EOFError('shutdown')
            continue
        if not chunk:
            raise EOFError('connection closed')
        chunks.extend(chunk)
    return bytes(chunks)


def read_frame(sock, max_bytes):
    hlen, plen = PREFIX.unpack(read_exact(sock, PREFIX.size))
    if not 0 < hlen <= MAX_HEADER or plen > max_bytes:
        raise ValueError('invalid frame size')
    header = json.loads(read_exact(sock, hlen).decode('utf-8'))
    return header, read_exact(sock, plen)
