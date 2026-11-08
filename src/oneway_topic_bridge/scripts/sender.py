#!/usr/bin/env python3
import queue
import socket
import threading

import os
import sys
import rospy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bridge_common import encode, settings


class Sender:
    def __init__(self):
        topics, size, self.max_bytes = settings()
        self.host = rospy.get_param('~receiver_ip', '127.0.0.1')
        self.port = int(rospy.get_param('~port', 19090))
        self.pending = queue.Queue(maxsize=size)
        self.lock = threading.Lock()
        self.subscribers = [rospy.Subscriber(t, rospy.AnyMsg, self.callback, callback_args=t, queue_size=size, buff_size=65536) for t in topics]
        threading.Thread(target=self.send_loop, daemon=True).start()
        rospy.loginfo('Sending topics: %s', ', '.join(topics))

    def callback(self, msg, topic):
        h = msg._connection_header
        try:
            header = {'topic': topic, 'type': h['type'], 'md5sum': h['md5sum'],
                      'definition': h['message_definition'], 'latching': h.get('latching', '0') == '1'}
            frame = encode(header, msg._buff, self.max_bytes)
        except (KeyError, ValueError) as exc:
            rospy.logwarn_throttle(5, 'Cannot forward %s: %s', topic, exc)
            return
        with self.lock:
            if self.pending.full():
                try:
                    self.pending.get_nowait()
                except queue.Empty:
                    pass
                rospy.logwarn_throttle(5, 'Bridge queue full; dropping oldest message')
            self.pending.put_nowait(frame)

    def send_loop(self):
        sock = None
        while not rospy.is_shutdown():
            if sock is None:
                try:
                    sock = socket.create_connection((self.host, self.port), timeout=2)
                    sock.settimeout(2)
                    rospy.loginfo('Connected to %s:%s', self.host, self.port)
                except OSError as exc:
                    rospy.logwarn_throttle(5, 'Waiting for receiver: %s', exc)
                    rospy.rostime.wallsleep(1)
                    continue
            try:
                frame = self.pending.get(timeout=0.5)
                sock.sendall(frame)
            except queue.Empty:
                continue
            except OSError as exc:
                rospy.logwarn('Connection lost; current message dropped: %s', exc)
                sock.close()
                sock = None
        if sock:
            sock.close()


if __name__ == '__main__':
    rospy.init_node('oneway_sender')
    try:
        Sender()
        rospy.spin()
    except (ValueError, TypeError) as exc:
        rospy.logfatal('Invalid configuration: %s', exc)
        raise
