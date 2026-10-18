from typing import Annotated

from fastapi import APIRouter, Depends

from app.routers.MirakcReservationsRouter import GetRecordingClient
from app.utils.mirakc.RecordingClient import MirakcRecordingClient, RecordingTuner


router = APIRouter(
    tags = ['Recording Tuners'],
    prefix = '/api/recording',
)


@router.get('/tuners', response_model=list[RecordingTuner])
async def RecordingTunersAPI(
    client: Annotated[MirakcRecordingClient, Depends(GetRecordingClient)],
) -> list[RecordingTuner]:
    return await client.listTuners()
