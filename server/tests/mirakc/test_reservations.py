import unittest

from app import schemas
from app.utils.mirakc.Reservations import EncodeRecordingOptions


class RecordingOptionsTest(unittest.TestCase):
    def test_repeated_recordings_do_not_reuse_content(self) -> None:
        settings = schemas.RecordSettings(is_event_relay_follow_enabled=False)
        first = EncodeRecordingOptions(settings, 10010100001)
        second = EncodeRecordingOptions(settings, 10010100001)
        self.assertNotEqual(first.content_path, second.content_path)
        self.assertEqual(first.priority, second.priority)

    def test_disabled_reservation_preserves_other_settings(self) -> None:
        settings = schemas.RecordSettings(is_enabled=False, priority=5,
                                          preferred_tuner_name='satellite', is_event_relay_follow_enabled=False)
        options = EncodeRecordingOptions(settings, 10010100001)
        self.assertTrue(options.disabled)
        self.assertEqual(options.priority, 2)
        self.assertEqual(options.preferred_tuner, 'satellite')
        settings.is_enabled = True
        self.assertFalse(EncodeRecordingOptions(settings, 10010100001).disabled)


if __name__ == '__main__':
    unittest.main()
