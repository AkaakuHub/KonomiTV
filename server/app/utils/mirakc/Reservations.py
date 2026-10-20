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
    supported = {'is_enabled', 'priority', 'preferred_tuner_name', 'recording_start_margin', 'recording_end_margin'}
    unsupported = settings.model_dump(exclude=supported)
    if unsupported != defaults.model_dump(exclude=supported):
        raise HTTPException(422, 'mirakcで未対応の録画設定が指定されています。')
    start_margin_ms = (settings.recording_start_margin if settings.recording_start_margin is not None else 5) * 1000
    end_margin_ms = (settings.recording_end_margin if settings.recording_end_margin is not None else 2) * 1000
    if not all(-2147483648 <= margin <= 2147483647 for margin in (start_margin_ms, end_margin_ms)):
        raise HTTPException(422, '録画マージンがmirakcの対応範囲外です。')
    return RecordingOptions(
        disabled=not settings.is_enabled,
        content_path=f'KonomiTV/{program_id}-{uuid4().hex}.ts',
        priority=settings.priority - 3,
        preferred_tuner=settings.preferred_tuner_name,
        start_margin_ms=start_margin_ms,
        end_margin_ms=end_margin_ms,
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
    start_margin_ms = schedule.options.start_margin_ms if schedule.options.start_margin_ms is not None else 2000
    end_margin_ms = schedule.options.end_margin_ms if schedule.options.end_margin_ms is not None else 2000
    if start_margin_ms % 1000 or end_margin_ms % 1000:
        raise HTTPException(502, 'mirakcの録画マージンが秒単位ではありません。')
    default_margins = (start_margin_ms, end_margin_ms) == (5000, 2000)
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
        comment='キーワード自動予約' if any(tag.startswith('KonomiTV-Auto:') for tag in schedule.tags) else '',
        scheduled_recording_file_name=PurePosixPath(schedule.options.content_path).name,
        estimated_recording_file_size=None,
        record_settings=schemas.RecordSettings(
            is_enabled=not schedule.options.disabled,
            priority=schedule.options.priority + 3,
            preferred_tuner_name=schedule.options.preferred_tuner,
            recording_start_margin=None if default_margins else start_margin_ms // 1000,
            recording_end_margin=None if default_margins else end_margin_ms // 1000,
            is_event_relay_follow_enabled=False,
        ),
    )
