from datetime import datetime, timedelta
from pathlib import PurePosixPath
from uuid import uuid4

from fastapi import HTTPException

from app import schemas
from app.constants import JST
from app.models.Channel import Channel
from app.models.Program import Program
from app.utils.mirakc.RecordingClient import RecordingOptions, RecordingSchedule


def EncodeRecordingOptions(settings: schemas.RecordSettings, program_id: int) -> RecordingOptions:
    defaults = schemas.RecordSettings(is_event_relay_follow_enabled=False)
    unsupported = settings.model_dump(exclude={'priority', 'preferred_tuner_name'})
    if unsupported != defaults.model_dump(exclude={'priority', 'preferred_tuner_name'}):
        raise HTTPException(422, 'mirakcで未対応の録画設定が指定されています。')
    return RecordingOptions(
        content_path=f'KonomiTV/{program_id}-{uuid4().hex}.ts',
        priority=settings.priority - 3,
        preferred_tuner=settings.preferred_tuner_name,
        pre_filters=[],
        post_filters=[],
    )


async def DecodeRecordingSchedule(schedule: RecordingSchedule) -> schemas.Reservation:
    source = schedule.program
    channel_id = f'NID{source.network_id}-SID{source.service_id:03d}'
    program_id = f'{channel_id}-EID{source.event_id}'
    program = await Program.get_or_none(id=program_id)
    channel = await Channel.get_or_none(id=channel_id)
    if program is None or channel is None:
        raise HTTPException(503, '予約番組の情報が番組表にありません。番組情報の更新を待ってください。')
    if source.start_at is None or source.duration is None or not 0 < source.duration:
        raise HTTPException(502, 'mirakcから予約番組の日時を取得できませんでした。')
    if not -2 <= schedule.options.priority <= 2:
        raise HTTPException(502, 'mirakcの予約優先度がKonomiTVの対応範囲外です。')
    start_time = datetime.fromtimestamp(source.start_at / 1000, JST)
    duration = source.duration / 1000
    metadata = schemas.Program.model_validate(program).model_copy(update=dict(
        start_time=start_time,
        end_time=start_time + timedelta(seconds=duration),
        duration=duration,
        title=source.name if source.name is not None else program.title,
        description=source.description if source.description is not None else program.description,
    ))
    return schemas.Reservation(
        id=source.id,
        channel=schemas.Channel.model_validate(channel),
        program=metadata,
        is_recording_in_progress=schedule.state == 'recording',
        recording_availability='Unknown',
        comment='',
        scheduled_recording_file_name=PurePosixPath(schedule.options.content_path).name,
        estimated_recording_file_size=None,
        record_settings=schemas.RecordSettings(
            priority=schedule.options.priority + 3,
            preferred_tuner_name=schedule.options.preferred_tuner,
            is_event_relay_follow_enabled=False,
        ),
    )
