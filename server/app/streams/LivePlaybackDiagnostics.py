from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, FiniteFloat


class LivePlaybackDiagnostics(BaseModel):
    revision: Literal['live-playback-20261021']
    session_id: UUID
    phase: Literal['initial', '5s', '15s', '30s', 'native-error', 'mpegts-error']
    user_agent: Annotated[str, Field(max_length=512)]
    player_type: Annotated[str, Field(max_length=32)]
    elapsed_seconds: FiniteFloat
    ready_state: Annotated[int, Field(ge=0, le=4)]
    network_state: Annotated[int, Field(ge=0, le=3)]
    current_time: FiniteFloat | None
    playback_rate: FiniteFloat
    paused: bool
    muted: bool
    volume: FiniteFloat
    width: int
    height: int
    decoded_frames: int | None
    dropped_frames: int | None
    buffered: Annotated[list[tuple[FiniteFloat, FiniteFloat]], Field(max_length=16)]
    video_codec: Annotated[str | None, Field(max_length=128)]
    audio_codec: Annotated[str | None, Field(max_length=128)]
    media_error_code: Annotated[int | None, Field(ge=1, le=4)]
    media_error: Annotated[str | None, Field(max_length=512)]
    mpegts_error: Annotated[str | None, Field(max_length=512)]
    media_source: bool
    managed_media_source: bool
    loading: bool
    buffering: bool
    program_id: Annotated[str | None, Field(max_length=64)]
