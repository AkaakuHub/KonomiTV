from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError

from app import logging, schemas
from app.config import Config
from app.constants import HTTPX_CLIENT
from app.models.Program import Program
from app.utils.mirakc.RecordingClient import (
    MirakcRecordingClient,
    RecordingScheduleInput,
)
from app.utils.mirakc.Reservations import (
    DecodeRecordingSchedule,
    EncodeRecordingOptions,
)


router = APIRouter(
    tags = ['Reservations'],
    prefix = '/api/recording/reservations',
)


async def GetRecordingClient() -> AsyncIterator[MirakcRecordingClient]:
    async with HTTPX_CLIENT() as client:
        try:
            yield MirakcRecordingClient(client, str(Config().general.mirakurun_url))
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code
            if status_code not in (400, 404, 409):
                status_code = status.HTTP_502_BAD_GATEWAY
            logging.warning(f'mirakc recording API returned HTTP {error.response.status_code}.')
            raise HTTPException(status_code, 'mirakcの録画予約APIでエラーが発生しました。') from error
        except (httpx.RequestError, ValidationError) as error:
            logging.warning('Failed to access mirakc recording schedules.', exc_info=error)
            raise HTTPException(502, 'mirakcの録画予約を取得できませんでした。') from error


@router.get('', response_model=schemas.Reservations)
async def ReservationsAPI(
    client: Annotated[MirakcRecordingClient, Depends(GetRecordingClient)],
) -> schemas.Reservations:
    schedules = await client.listSchedules()
    reservations = [
        await DecodeRecordingSchedule(schedule)
        for schedule in schedules
        if schedule.state not in ('finished', 'failed')
    ]
    reservations.sort(key=lambda reservation: reservation.program.start_time)
    return schemas.Reservations(total=len(reservations), reservations=reservations)


@router.post('', status_code=status.HTTP_201_CREATED)
async def AddReservationAPI(
    request: schemas.ReservationAddRequest,
    client: Annotated[MirakcRecordingClient, Depends(GetRecordingClient)],
) -> None:
    program = await Program.get_or_none(id=request.program_id)
    if program is None:
        raise HTTPException(422, '番組表に指定の番組がありません。')
    program_id = (program.network_id * 100000 + program.service_id) * 100000 + program.event_id
    options = EncodeRecordingOptions(request.record_settings, program_id)
    await client.createSchedule(RecordingScheduleInput(program_id=program_id, options=options, tags=['KonomiTV']))


@router.get('/{reservation_id}', response_model=schemas.Reservation)
async def ReservationAPI(
    reservation_id: int,
    client: Annotated[MirakcRecordingClient, Depends(GetRecordingClient)],
) -> schemas.Reservation:
    return await DecodeRecordingSchedule(await client.getSchedule(reservation_id))


@router.put('/{reservation_id}', response_model=schemas.Reservation)
async def ReservationUpdateAPI(
    reservation_id: int,
    request: schemas.ReservationUpdateRequest,
    client: Annotated[MirakcRecordingClient, Depends(GetRecordingClient)],
) -> schemas.Reservation:
    options = EncodeRecordingOptions(request.record_settings, reservation_id)
    schedule = await client.getSchedule(reservation_id)
    schedule.options.priority = options.priority
    return await DecodeRecordingSchedule(await client.updateSchedule(schedule))


@router.delete('/{reservation_id}', status_code=status.HTTP_204_NO_CONTENT)
async def DeleteReservationAPI(
    reservation_id: int,
    client: Annotated[MirakcRecordingClient, Depends(GetRecordingClient)],
) -> None:
    await client.deleteSchedule(reservation_id)
