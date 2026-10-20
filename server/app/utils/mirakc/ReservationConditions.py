import asyncio
from datetime import datetime, timedelta

import httpx

from app import logging, schemas
from app.constants import JST
from app.models.MirakcReservationCondition import (
    MirakcRecordingExclusion,
    MirakcReservationCondition,
)
from app.models.RecordedProgram import RecordedProgram
from app.utils.mirakc.ProgramSearch import SearchPrograms
from app.utils.mirakc.RecordingClient import (
    MirakcRecordingClient,
    RecordingSchedule,
    RecordingScheduleInput,
)
from app.utils.mirakc.Reservations import EncodeRecordingOptions


reservation_lock = asyncio.Lock()


def ConditionTag(condition_id: int) -> str:
    return f'KonomiTV-Auto:{condition_id}'


def DecodeCondition(condition: MirakcReservationCondition, schedules: list[RecordingSchedule]) -> schemas.ReservationCondition:
    return schemas.ReservationCondition(
        id=condition.id,
        reservation_count=sum(
            ConditionTag(condition.id) in schedule.tags and schedule.state not in ('finished', 'failed')
            for schedule in schedules
        ),
        program_search_condition=schemas.ProgramSearchCondition.model_validate_json(condition.program_search_condition),
        record_settings=schemas.RecordSettings.model_validate_json(condition.record_settings),
    )


async def HasRecordedDuplicate(condition: schemas.ProgramSearchCondition, program: schemas.Program) -> bool:
    if condition.duplicate_title_check_scope == 'None':
        return False
    recordings = RecordedProgram.filter(
        title=program.title,
        start_time__gt=program.start_time - timedelta(days=condition.duplicate_title_check_period_days),
        recorded_video__status='Recorded',
    )
    if condition.duplicate_title_check_scope == 'SameChannelOnly':
        recordings = recordings.filter(channel_id=program.channel_id)
    return await recordings.exists()


async def UpdateReservations(client: MirakcRecordingClient) -> None:
    async with reservation_lock:
        conditions = await MirakcReservationCondition.all().order_by('id')
        if not conditions:
            return
        now = datetime.now(JST)
        await MirakcRecordingExclusion.filter(end_time__lte=now).delete()
        excluded = {exclusion.program_id for exclusion in await MirakcRecordingExclusion.all()}
        schedules = {schedule.program.id: schedule for schedule in await client.listSchedules()}
        for row in conditions:
            condition = schemas.ProgramSearchCondition.model_validate_json(row.program_search_condition)
            if not condition.is_enabled:
                continue
            settings = schemas.RecordSettings.model_validate_json(row.record_settings)
            for program in await SearchPrograms(condition):
                program_id = (program.network_id * 100000 + program.service_id) * 100000 + program.event_id
                existing = schedules.get(program_id)
                if existing is not None:
                    if (ConditionTag(row.id) in existing.tags and not existing.options.disabled and
                        existing.state in ('scheduled', 'tracking', 'rescheduling') and
                        await HasRecordedDuplicate(condition, program)):
                        existing.options.disabled = True
                        try:
                            schedules[program_id] = await client.updateSchedule(existing)
                        except httpx.HTTPStatusError as error:
                            if error.response.status_code != 409:
                                raise
                            schedules[program_id] = await client.getSchedule(program_id)
                    continue
                if program.start_time < now or program_id in excluded:
                    continue
                options = EncodeRecordingOptions(settings, program_id)
                if await HasRecordedDuplicate(condition, program):
                    options.disabled = True
                try:
                    schedule = await client.createSchedule(RecordingScheduleInput(
                        program_id=program_id,
                        options=options,
                        tags=['KonomiTV', ConditionTag(row.id)],
                    ))
                    schedules[program_id] = schedule
                    logging.info(f'[MirakcAutoReservation] Added program {program_id} for condition {row.id}.')
                except httpx.HTTPStatusError as error:
                    if error.response.status_code == 400:
                        try:
                            schedules[program_id] = await client.getSchedule(program_id)
                        except httpx.HTTPStatusError as lookup_error:
                            if lookup_error.response.status_code != 404:
                                raise
                            logging.warning(f'[MirakcAutoReservation] Program {program_id} can no longer be scheduled.')
                    elif error.response.status_code == 404:
                        logging.warning(f'[MirakcAutoReservation] Program {program_id} is no longer in mirakc EPG.')
                    else:
                        raise
