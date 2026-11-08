#!/usr/bin/env python3
import io
import os
import struct
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import rospy
from sensor_msgs.msg import Image
from std_msgs.msg import String
from bridge_common import PREFIX, encode, read_frame, settings
from receiver import Receiver


class FragmentedSocket:
    def __init__(self, data):
        self.data = data
    def recv(self, count):
        data, self.data = self.data[:min(3, count)], self.data[min(3, count):]
        return data


class Publisher:
    def __init__(self, name, cls, **kwargs):
        self.name, self.cls, self.kwargs = name, cls, kwargs
        self.messages = []
        self.unregistered = False
    def publish(self, msg):
        self.messages.append(msg._buff)
    def unregister(self):
        self.unregistered = True


def serialized(msg):
    buf = io.BytesIO()
    msg.serialize(buf)
    return buf.getvalue()


def header(msg, topic='/test', latch=False):
    return dict(topic=topic, type=msg._type, md5sum=msg._md5sum,
                definition=msg._full_text, latching=latch)


class Tests(unittest.TestCase):
    def test_roundtrip_real_ros_types_and_fragmentation(self):
        image = Image(height=2, width=3, encoding='mono8', step=3, data=bytes([0, 1, 2, 253, 254, 255]))
        for original in (String(data='中文 hello'), image):
            payload = serialized(original)
            meta = header(original)
            actual, data = read_frame(FragmentedSocket(encode(meta, payload, 1024 * 1024)), 1024 * 1024)
            self.assertEqual(actual, meta)
            restored = type(original)().deserialize(data)
            self.assertEqual(restored, original)

    def test_limits_and_truncated_frame(self):
        with self.assertRaises(ValueError):
            encode({}, b'123', 2)
        with self.assertRaises(ValueError):
            read_frame(FragmentedSocket(PREFIX.pack(1, 10)), 9)
        with self.assertRaises(EOFError):
            read_frame(FragmentedSocket(PREFIX.pack(5, 0) + b'{}'), 100)

    def test_receiver_preserves_type_metadata_bytes_and_latch(self):
        receiver = Receiver.__new__(Receiver)
        receiver.allowed, receiver.publishers, receiver.queue_size = {'/test'}, {}, 10
        original = String(data='内容')
        with patch('receiver.rospy.Publisher', side_effect=Publisher):
            receiver.publish(header(original, latch=True), serialized(original))
            identity, pub, cls = receiver.publishers['/test']
            self.assertEqual((cls._type, cls._md5sum, cls._full_text), (original._type, original._md5sum, original._full_text))
            self.assertTrue(pub.kwargs['latch'])
            self.assertEqual(String().deserialize(pub.messages[0]), original)
            receiver.publish(header(original, latch=False), serialized(original))
            self.assertTrue(pub.unregistered)
            with self.assertRaises(ValueError):
                receiver.publish(header(original, topic='/forbidden'), b'')

    def test_config_validation(self):
        def params(name, default):
            return {'~topics': ['/test', '/test'], '~queue_size': 10, '~max_message_bytes': 100}[name]
        with patch('bridge_common.rospy.get_param', side_effect=params):
            with self.assertRaises(ValueError):
                settings()


if __name__ == '__main__':
    unittest.main()
