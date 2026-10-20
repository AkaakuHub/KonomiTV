import unittest
from datetime import datetime, timedelta

from test_program_search import MakeProgram
from tortoise import Tortoise

from app import schemas
from app.constants import DATABASE_CONFIG, JST
from app.models.Channel import Channel
from app.models.Program import Program
from app.utils.mirakc.ProgramSearch import SearchPrograms


class ProgramSearchDatabaseTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await Tortoise.init(config={**DATABASE_CONFIG, 'connections': {'default': 'sqlite://:memory:'}})
        await Tortoise.generate_schemas()
        await Channel.create(
            id='NID1-SID101', display_channel_id='bs101', network_id=1, service_id=101,
            remocon_id=1, channel_number='101', type='BS', name='テスト',
            is_subchannel=False, is_radiochannel=False, is_watchable=True,
        )
        self.start = datetime.now(JST) + timedelta(hours=1)
        await Program.bulk_create([
            Program(**MakeProgram(
                id=f'NID1-SID101-EID{index}', event_id=index,
                title='映画' if index % 2 else 'ニュース',
                start_time=self.start + timedelta(minutes=index),
                end_time=self.start + timedelta(minutes=index + 30), duration=1800,
            ).model_dump())
            for index in range(300)
        ])

    async def asyncTearDown(self) -> None:
        await Tortoise.close_connections()

    async def test_search_returns_all_matches_in_broadcast_order(self) -> None:
        programs = await SearchPrograms(schemas.ProgramSearchCondition(keyword='映画'))
        self.assertEqual([program.event_id for program in programs], list(range(1, 300, 2)))
        self.assertEqual(programs[-1].start_time, self.start + timedelta(minutes=299))

    async def test_empty_keyword_keeps_all_programs(self) -> None:
        programs = await SearchPrograms(schemas.ProgramSearchCondition())
        self.assertEqual([program.event_id for program in programs], list(range(300)))


if __name__ == '__main__':
    unittest.main()
