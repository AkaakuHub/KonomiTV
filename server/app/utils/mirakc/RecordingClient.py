from typing import Annotated, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class RecordingSchedule(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    state: Literal['scheduled', 'tracking', 'recording', 'rescheduling', 'finished', 'failed']
    program: 'RecordingProgram'
    options: 'RecordingOptions'
    tags: list[str]


class RecordingProgram(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    network_id: Annotated[int, Field(alias='networkId')]
    service_id: Annotated[int, Field(alias='serviceId')]
    event_id: Annotated[int, Field(alias='eventId')]
    start_at: Annotated[int | None, Field(alias='startAt')] = None
    duration: int | None = None
    name: str | None = None
    description: str | None = None


class RecordingOptions(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    content_path: Annotated[str, Field(alias='contentPath')]
    priority: Annotated[int, Field(ge=-2147483648, le=2147483647)] = 0
    pre_filters: Annotated[list[str], Field(alias='preFilters', default_factory=list)]
    post_filters: Annotated[list[str], Field(alias='postFilters', default_factory=list)]


class RecordingScheduleInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    program_id: Annotated[int, Field(alias='programId')]
    options: RecordingOptions
    tags: Annotated[list[str], Field(default_factory=list)]


class MirakcRecordingClient:
    """mirakcの録画予約APIへアクセスし、応答を検証する。"""

    def __init__(self, client: httpx.AsyncClient, base_url: str) -> None:
        self.client = client
        self.endpoint = base_url.rstrip('/') + '/api/recording/schedules'

    async def listSchedules(self) -> list[RecordingSchedule]:
        response = await self.client.get(self.endpoint)
        response.raise_for_status()
        return TypeAdapter(list[RecordingSchedule]).validate_json(response.content)

    async def getSchedule(self, program_id: int) -> RecordingSchedule:
        response = await self.client.get(f'{self.endpoint}/{program_id}')
        response.raise_for_status()
        return RecordingSchedule.model_validate_json(response.content)

    async def createSchedule(self, schedule: RecordingScheduleInput) -> RecordingSchedule:
        response = await self.client.post(self.endpoint, json=schedule.model_dump(by_alias=True))
        response.raise_for_status()
        return RecordingSchedule.model_validate_json(response.content)

    async def deleteSchedule(self, program_id: int) -> None:
        response = await self.client.delete(f'{self.endpoint}/{program_id}')
        response.raise_for_status()
