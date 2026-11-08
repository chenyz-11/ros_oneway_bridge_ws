#!/usr/bin/env python3
import re
import socket

import os
import sys
import rospy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bridge_common import read_frame, settings


class Receiver:
    def __init__(self):
        topics, self.queue_size, self.max_bytes = settings()
        self.allowed = set(topics)
        self.publishers = {}
        self.host = rospy.get_param('~bind_ip', '0.0.0.0')
        self.port = int(rospy.get_param('~port', 19090))

    def publish(self, header, payload):
        if not isinstance(header, dict):
            raise ValueError('invalid header')
        topic, typ, md5, definition, latch = (header.get(k) for k in ('topic', 'type', 'md5sum', 'definition', 'latching'))
        if topic not in self.allowed or not isinstance(typ, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*/[A-Za-z][A-Za-z0-9_]*', typ) or not isinstance(md5, str) or not re.fullmatch(r'[0-9a-f]{32}', md5) or not isinstance(definition, str) or type(latch) is not bool:
            raise ValueError('invalid or disallowed topic metadata')
        identity = (typ, md5, definition, latch)
        if topic in self.publishers and self.publishers[topic][0] != identity:
            rospy.logwarn('Metadata changed for %s; recreating publisher', topic)
            self.publishers.pop(topic)[1].unregister()
        if topic not in self.publishers:
            cls = type('ForwardedMessage', (rospy.AnyMsg,), {'_type': typ, '_md5sum': md5, '_full_text': definition})
            pub = rospy.Publisher(topic, cls, queue_size=self.queue_size, latch=latch)
            self.publishers[topic] = (identity, pub, cls)
            rospy.loginfo('Publishing %s (%s, latch=%s)', topic, typ, latch)
        _, pub, cls = self.publishers[topic]
        msg = cls()
        msg._buff = payload
        pub.publish(msg)

    def run(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((self.host, self.port))
            server.listen(1)
            server.settimeout(1)
            rospy.loginfo('Listening on %s:%s', self.host, self.port)
            while not rospy.is_shutdown():
                try:
                    conn, address = server.accept()
                except socket.timeout:
                    continue
                rospy.loginfo('Sender connected: %s', address)
                with conn:
                    conn.settimeout(1)
                    try:
                        while not rospy.is_shutdown():
                            header, payload = read_frame(conn, self.max_bytes)
                            self.publish(header, payload)
                    except (EOFError, OSError, ValueError, UnicodeError, TypeError) as exc:
                        rospy.logwarn('Sender disconnected: %s', exc)


if __name__ == '__main__':
    rospy.init_node('oneway_receiver')
    try:
        Receiver().run()
    except (ValueError, TypeError, OSError) as exc:
        rospy.logfatal('Receiver failed: %s', exc)
        raise
