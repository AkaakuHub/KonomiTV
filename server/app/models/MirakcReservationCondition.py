from tortoise import fields
from tortoise.models import Model


class MirakcReservationCondition(Model):
    class Meta(Model.Meta):
        table = 'mirakc_reservation_conditions'

    id = fields.IntField(pk=True)
    program_search_condition = fields.TextField()
    record_settings = fields.TextField()


class MirakcRecordingExclusion(Model):
    class Meta(Model.Meta):
        table = 'mirakc_recording_exclusions'

    program_id = fields.BigIntField(pk=True)
    end_time = fields.DatetimeField(index=True)
