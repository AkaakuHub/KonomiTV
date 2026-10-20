import unittest
from datetime import datetime, timedelta

import httpx
from fastapi import HTTPException
from test_program_search import MakeProgram
from tortoise import Tortoise

from app import schemas
from app.constants import DATABASE_CONFIG, JST
from app.models.Channel import Channel
from app.models.MirakcReservationCondition import (
    MirakcRecordingExclusion,
    MirakcReservationCondition,
)
from app.models.Program import Program
from app.models.RecordedProgram import RecordedProgram
from app.models.RecordedVideo import RecordedVideo
from app.routers.MirakcReservationConditionsRouter import (
    DeleteReservationConditionAPI,
    RegisterReservationConditionAPI,
    UpdateReservationConditionAPI,
)
from app.routers.MirakcReservationsRouter import DeleteReservationAPI
from app.utils.mirakc.RecordingClient import MirakcRecordingClient, RecordingSchedule
from app.utils.mirakc.ReservationConditions import (
    DecodeCondition,
    HasRecordedDuplicate,
    UpdateReservations,
)


class ReservationConditionsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await Tortoise.init(config={**DATABASE_CONFIG, 'connections': {'default': 'sqlite://:memory:'}})
        await Tortoise.generate_schemas()
        await Channel.create(
            id='NID1-SID101', display_channel_id='bs101', network_id=1, service_id=101,
            remocon_id=1, channel_number='101', type='BS', name='テスト',
            is_subchannel=False, is_radiochannel=False, is_watchable=True,
        )
        self.program = MakeProgram(start_time=datetime.now(JST) + timedelta(hours=1),
                                   end_time=datetime.now(JST) + timedelta(hours=3))
        await Program.create(**self.program.model_dump())
        self.schedules: dict[int, RecordingSchedule] = {}
        self.created = 0
        self.http = httpx.AsyncClient(transport=httpx.MockTransport(self.respond))
        self.client = MirakcRecordingClient(self.http, 'http://mirakc')
        self.settings = schemas.RecordSettings(is_event_relay_follow_enabled=False)

    async def asyncTearDown(self) -> None:
        await self.http.aclose()
        await Tortoise.close_connections()

    def respond(self, request: httpx.Request) -> httpx.Response:
        if request.method == 'GET' and request.url.path.endswith('/schedules'):
            return httpx.Response(200, json=[schedule.model_dump(by_alias=True) for schedule in self.schedules.values()])
        program_id = (self.program.network_id * 100000 + self.program.service_id) * 100000 + self.program.event_id
        if request.method == 'POST':
            from app.utils.mirakc.RecordingClient import (
                RecordingProgram,
                RecordingScheduleInput,
            )
            data = RecordingScheduleInput.model_validate_json(request.content)
            if data.program_id in self.schedules:
                return httpx.Response(409)
            schedule = RecordingSchedule(
                state='scheduled', options=data.options, tags=data.tags,
                program=RecordingProgram(
                    id=program_id, network_id=1, service_id=101, event_id=1,
                    start_at=int(self.program.start_time.timestamp() * 1000), duration=7200000,
                ),
            )
            self.schedules[program_id] = schedule
            self.created += 1
            return httpx.Response(201, json=schedule.model_dump(by_alias=True))
        schedule = self.schedules.get(program_id)
        if schedule is None:
            return httpx.Response(404)
        if request.method == 'DELETE':
            del self.schedules[program_id]
            return httpx.Response(204)
        return httpx.Response(200, json=schedule.model_dump(by_alias=True))

    async def addCondition(self, keyword: str = '映画', enabled: bool = True) -> MirakcReservationCondition:
        await RegisterReservationConditionAPI(schemas.ReservationConditionAddRequest(
            program_search_condition=schemas.ProgramSearchCondition(keyword=keyword, is_enabled=enabled),
            record_settings=self.settings,
        ))
        return await MirakcReservationCondition.all().order_by('-id').first() or self.fail('Condition was not saved')

    async def test_persisted_condition_schedules_once(self) -> None:
        row = await self.addCondition()
        self.assertEqual(schemas.ProgramSearchCondition.model_validate_json(row.program_search_condition).keyword, '映画')
        await UpdateReservations(self.client)
        await UpdateReservations(self.client)
        self.assertEqual(self.created, 1)
        condition = DecodeCondition(row, list(self.schedules.values()))
        self.assertEqual(condition.reservation_count, 1)
        self.assertIn(f'KonomiTV-Auto:{row.id}', next(iter(self.schedules.values())).tags)

    async def test_overlapping_conditions_preserve_existing_reservation(self) -> None:
        await self.addCondition()
        await self.addCondition('ABC')
        await UpdateReservations(self.client)
        schedule = next(iter(self.schedules.values()))
        schedule.tags = ['manual']
        schedule.options.priority = 2
        await UpdateReservations(self.client)
        self.assertEqual(self.created, 1)
        self.assertEqual(schedule.tags, ['manual'])
        self.assertEqual(schedule.options.priority, 2)

    async def test_deleted_reservation_is_not_recreated(self) -> None:
        await self.addCondition()
        await UpdateReservations(self.client)
        await DeleteReservationAPI(next(iter(self.schedules)), self.client)
        await UpdateReservations(self.client)
        self.assertEqual(self.created, 1)
        self.assertEqual(self.schedules, {})
        self.assertEqual(await MirakcRecordingExclusion.all().count(), 1)

    async def test_disabled_condition_and_update(self) -> None:
        row = await self.addCondition(enabled=False)
        await UpdateReservations(self.client)
        self.assertEqual(self.created, 0)
        await UpdateReservationConditionAPI(row.id, schemas.ReservationConditionUpdateRequest(
            program_search_condition=schemas.ProgramSearchCondition(keyword='映画'), record_settings=self.settings,
        ), self.client)
        await UpdateReservations(self.client)
        self.assertEqual(self.created, 1)

    async def test_delete_condition_retains_existing_schedules(self) -> None:
        row = await self.addCondition()
        await UpdateReservations(self.client)
        await DeleteReservationConditionAPI(row.id)
        await UpdateReservations(self.client)
        self.assertEqual(await MirakcReservationCondition.all().count(), 0)
        self.assertEqual(len(self.schedules), 1)

    async def test_unsupported_settings_are_not_saved(self) -> None:
        self.settings.is_enabled = False
        with self.assertRaises(HTTPException):
            await self.addCondition()
        self.assertEqual(await MirakcReservationCondition.all().count(), 0)

    async def test_unknown_condition(self) -> None:
        with self.assertRaises(HTTPException) as error:
            await DeleteReservationConditionAPI(999)
        self.assertEqual(error.exception.status_code, 404)

    async def test_unwatchable_and_expired_programs_are_not_scheduled(self) -> None:
        await self.addCondition()
        await Channel.filter(id=self.program.channel_id).update(is_watchable=False)
        await UpdateReservations(self.client)
        self.assertEqual(self.created, 0)
        await Channel.filter(id=self.program.channel_id).update(is_watchable=True)
        await Program.filter(id=self.program.id).update(end_time=datetime.now(JST) - timedelta(seconds=1))
        await UpdateReservations(self.client)
        self.assertEqual(self.created, 0)

    async def test_recorded_duplicate_scope_and_period(self) -> None:
        recorded = await RecordedProgram.create(
            **self.program.model_dump(exclude={'id', 'video_type', 'video_codec', 'video_resolution',
                                               'primary_audio_sampling_rate', 'secondary_audio_sampling_rate'}),
            recording_start_margin=0, recording_end_margin=0, is_partially_recorded=False,
        )
        await RecordedVideo.create(
            recorded_program=recorded, status='Recorded', file_path='/recordings/test.ts', file_hash='test',
            file_size=1000, file_created_at=datetime.now(JST), file_modified_at=datetime.now(JST),
            duration=7200, container_format='MPEG-TS', video_codec='MPEG-2', video_codec_profile='Main',
            video_scan_type='Interlaced', video_frame_rate=29.97, video_resolution_width=1920,
            video_resolution_height=1080, primary_audio_codec='AAC-LC', primary_audio_channel='Stereo',
            primary_audio_sampling_rate=48000,
        )
        condition = schemas.ProgramSearchCondition(duplicate_title_check_scope='SameChannelOnly')
        self.assertTrue(await HasRecordedDuplicate(condition, self.program))
        await RecordedProgram.filter(id=recorded.id).update(channel_id=None)
        self.assertFalse(await HasRecordedDuplicate(condition, self.program))
        condition.duplicate_title_check_scope = 'AllChannels'
        self.assertTrue(await HasRecordedDuplicate(condition, self.program))
        await RecordedProgram.filter(id=recorded.id).update(start_time=datetime.now(JST) - timedelta(days=7))
        self.assertFalse(await HasRecordedDuplicate(condition, self.program))


if __name__ == '__main__':
    unittest.main()
