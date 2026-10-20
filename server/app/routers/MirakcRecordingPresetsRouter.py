from fastapi import APIRouter

from app import schemas


router = APIRouter(
    tags = ['Recording Presets'],
    prefix = '/api/recording',
)


@router.get('/presets', response_model=schemas.RecordSettingsPresets)
async def RecordingPresetsAPI() -> schemas.RecordSettingsPresets:
    return schemas.RecordSettingsPresets(
        global_defaults=None,
        presets=[schemas.RecordSettingsPreset(
            id=0,
            name='デフォルト',
            record_settings=schemas.RecordSettings(is_event_relay_follow_enabled=False),
        )],
    )
