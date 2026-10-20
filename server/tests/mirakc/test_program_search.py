import unittest
from datetime import datetime, timedelta

from fastapi import HTTPException

from app import schemas
from app.constants import JST
from app.utils.mirakc.ProgramSearch import (
    MatchesFuzzyKeyword,
    NormalizeSearchText,
    ProgramMatcher,
)


def MakeProgram(**updates: object) -> schemas.Program:
    start = datetime(2026, 10, 24, 23, 30, tzinfo=JST)
    data: dict[str, object] = dict(
        id='NID1-SID101-EID1', channel_id='NID1-SID101', network_id=1, service_id=101, event_id=1,
        title='映画 ABC ガイド', description='週末の特集', detail={'出演者': '山田太郎'},
        start_time=start, end_time=start + timedelta(hours=2), duration=7200, is_free=True,
        genres=[schemas.Genre(major='映画', middle='洋画')], video_type=None, video_codec=None,
        video_resolution=None, primary_audio_type='ステレオ', primary_audio_language='日本語',
        primary_audio_sampling_rate='48kHz', secondary_audio_type=None, secondary_audio_language=None,
        secondary_audio_sampling_rate=None,
    )
    data.update(updates)
    return schemas.Program.model_validate(data)


class ProgramSearchTest(unittest.TestCase):
    def matches(self, **condition: object) -> bool:
        return ProgramMatcher(schemas.ProgramSearchCondition.model_validate(condition)).matches(MakeProgram())

    def test_and_or_and_exclusion(self) -> None:
        self.assertTrue(self.matches(keyword='映画 ABC | スポーツ'))
        self.assertFalse(self.matches(keyword='映画 スポーツ'))
        self.assertFalse(self.matches(keyword='映画', exclude_keyword='スポーツ 特集'))
        self.assertTrue(self.matches(keyword='映画', exclude_keyword='スポーツ'))

    def test_title_detail_and_explicit_target(self) -> None:
        self.assertTrue(self.matches(keyword='山田太郎'))
        self.assertFalse(self.matches(keyword='山田太郎', is_title_only=True))
        self.assertTrue(self.matches(keyword=':genre:洋画', is_title_only=True))
        self.assertFalse(self.matches(keyword=':title:山田太郎'))

    def test_case_and_width(self) -> None:
        self.assertTrue(self.matches(keyword='ａｂｃ'))
        self.assertFalse(self.matches(keyword='abc', is_case_sensitive=True))
        self.assertTrue(self.matches(keyword='ＡＢＣ', is_case_sensitive=True))
        self.assertEqual(NormalizeSearchText('ｶﾞｲﾄﾞ　ＡＢＣ'), 'ガイド ABC')

    def test_regex_validation_and_exclusion(self) -> None:
        self.assertTrue(self.matches(keyword=r'^映画.*ABC', is_regex_search_enabled=True))
        self.assertFalse(self.matches(keyword='映画', exclude_keyword='A.C', is_regex_search_enabled=True))
        with self.assertRaises(HTTPException):
            ProgramMatcher(schemas.ProgramSearchCondition(keyword='[', is_regex_search_enabled=True))

    def test_fuzzy_edit_distance(self) -> None:
        self.assertTrue(MatchesFuzzyKeyword('ABCD', '前ABCX後'))
        self.assertFalse(MatchesFuzzyKeyword('ABCD', '前ABXY後'))
        self.assertFalse(MatchesFuzzyKeyword('ABC', 'ABX'))
        self.assertTrue(self.matches(keyword='映画 ABCX', is_fuzzy_search_enabled=True))

    def test_service_selection(self) -> None:
        self.assertTrue(self.matches(service_ranges=[dict(network_id=1, transport_stream_id=0, service_id=101)]))
        self.assertFalse(self.matches(service_ranges=[]))
        self.assertFalse(self.matches(service_ranges=[dict(network_id=2, transport_stream_id=0, service_id=101)]))

    def test_genre_and_inverse(self) -> None:
        self.assertTrue(self.matches(genre_ranges=[dict(major='映画', middle='すべて')]))
        self.assertFalse(self.matches(genre_ranges=[dict(major='映画', middle='洋画')], is_exclude_genre_ranges=True))
        self.assertFalse(self.matches(genre_ranges=[dict(major='映画', middle='邦画')]))

    def test_week_boundary_and_inclusive_end(self) -> None:
        date = dict(start_day_of_week=6, start_hour=23, start_minute=30,
                    end_day_of_week=0, end_hour=1, end_minute=0)
        self.assertTrue(self.matches(date_ranges=[date]))
        self.assertFalse(self.matches(date_ranges=[date], is_exclude_date_ranges=True))
        date.update(start_day_of_week=5, end_day_of_week=6, end_hour=23, end_minute=30)
        self.assertTrue(self.matches(date_ranges=[date]))

    def test_duration_and_broadcast(self) -> None:
        self.assertTrue(self.matches(duration_range_min=120, duration_range_max=120, broadcast_type='FreeOnly'))
        self.assertFalse(self.matches(duration_range_min=121))
        self.assertFalse(self.matches(duration_range_max=119))
        self.assertFalse(self.matches(broadcast_type='PaidOnly'))
        with self.assertRaises(HTTPException):
            ProgramMatcher(schemas.ProgramSearchCondition(duration_range_min=10, duration_range_max=1))

    def test_disabled(self) -> None:
        self.assertFalse(self.matches(is_enabled=False))


if __name__ == '__main__':
    unittest.main()
