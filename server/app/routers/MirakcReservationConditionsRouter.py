from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app import schemas
from app.models.MirakcReservationCondition import MirakcReservationCondition
from app.routers.MirakcReservationsRouter import GetRecordingClient
from app.utils.mirakc.ProgramSearch import ProgramMatcher
from app.utils.mirakc.RecordingClient import MirakcRecordingClient
from app.utils.mirakc.ReservationConditions import DecodeCondition, reservation_lock
from app.utils.mirakc.Reservations import EncodeRecordingOptions


router = APIRouter(tags=['Reservation Conditions'], prefix='/api/recording/conditions')


async def GetCondition(reservation_condition_id: int) -> MirakcReservationCondition:
    condition = await MirakcReservationCondition.get_or_none(id=reservation_condition_id)
    if condition is None:
        raise HTTPException(404, 'Specified reservation_condition_id was not found')
    return condition


@router.get('', response_model=schemas.ReservationConditions)
async def ReservationConditionsAPI(
    client: Annotated[MirakcRecordingClient, Depends(GetRecordingClient)],
) -> schemas.ReservationConditions:
    conditions = await MirakcReservationCondition.all().order_by('id')
    schedules = await client.listSchedules()
    return schemas.ReservationConditions(
        total=len(conditions),
        reservation_conditions=[DecodeCondition(condition, schedules) for condition in conditions],
    )


@router.post('', status_code=status.HTTP_201_CREATED)
async def RegisterReservationConditionAPI(request: schemas.ReservationConditionAddRequest) -> None:
    ProgramMatcher(request.program_search_condition)
    EncodeRecordingOptions(request.record_settings, 0)
    async with reservation_lock:
        await MirakcReservationCondition.create(
            program_search_condition=request.program_search_condition.model_dump_json(),
            record_settings=request.record_settings.model_dump_json(),
        )


@router.get('/{reservation_condition_id}', response_model=schemas.ReservationCondition)
async def ReservationConditionAPI(
    condition: Annotated[MirakcReservationCondition, Depends(GetCondition)],
    client: Annotated[MirakcRecordingClient, Depends(GetRecordingClient)],
) -> schemas.ReservationCondition:
    return DecodeCondition(condition, await client.listSchedules())


@router.put('/{reservation_condition_id}', response_model=schemas.ReservationCondition)
async def UpdateReservationConditionAPI(
    reservation_condition_id: int,
    request: schemas.ReservationConditionUpdateRequest,
    client: Annotated[MirakcRecordingClient, Depends(GetRecordingClient)],
) -> schemas.ReservationCondition:
    ProgramMatcher(request.program_search_condition)
    EncodeRecordingOptions(request.record_settings, 0)
    async with reservation_lock:
        condition = await GetCondition(reservation_condition_id)
        condition.program_search_condition = request.program_search_condition.model_dump_json()
        condition.record_settings = request.record_settings.model_dump_json()
        await condition.save()
    return DecodeCondition(condition, await client.listSchedules())


@router.delete('/{reservation_condition_id}', status_code=status.HTTP_204_NO_CONTENT)
async def DeleteReservationConditionAPI(reservation_condition_id: int) -> None:
    async with reservation_lock:
        condition = await GetCondition(reservation_condition_id)
        await condition.delete()
