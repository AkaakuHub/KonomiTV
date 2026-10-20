import asyncio
import re
import unicodedata
from datetime import datetime

from fastapi import HTTPException
from pydantic import TypeAdapter
from tortoise.transactions import in_transaction

from app import schemas
from app.constants import JST
from app.models.Program import Program


def NormalizeSearchText(text: str) -> str:
    text = re.sub(r'[\uff61-\uff9f]+', lambda match: unicodedata.normalize('NFKC', match[0]), text)
    return text.translate(str.maketrans({
        **{chr(code): chr(code - 0xfee0) for code in range(0xff01, 0xff5f)},
        '　': ' ', '’': "'", '”': '"', '￥': '\\',
    }))


def MatchesFuzzyKeyword(keyword: str, text: str) -> bool:
    previous = list(range(len(keyword) + 1))
    for character in text:
        current = [0]
        for index, expected in enumerate(keyword):
            current.append(min(
                previous[index] + (character != expected),
                previous[index + 1] + 1,
                current[index] + 1,
            ))
        if current[-1] * 4 <= len(keyword):
            return True
        previous = current
    return False


class ProgramMatcher:
    """番組検索と自動予約で同じ検索条件を評価する。"""

    def __init__(self, condition: schemas.ProgramSearchCondition) -> None:
        self.condition = condition
        self.patterns: list[re.Pattern[str] | None] = [None, None]
        if condition.is_regex_search_enabled:
            try:
                self.patterns = [
                    re.compile(keyword, 0 if condition.is_case_sensitive else re.IGNORECASE) if keyword else None
                    for keyword in (condition.keyword, condition.exclude_keyword)
                ]
            except re.error as error:
                raise HTTPException(422, '正規表現が正しくありません。') from error
        if (condition.duration_range_min is not None and condition.duration_range_max is not None and
            condition.duration_range_min > condition.duration_range_max):
            raise HTTPException(422, '番組長の最小値は最大値以下にしてください。')

    def matches(self, program: schemas.Program) -> bool:
        condition = self.condition
        if not condition.is_enabled:
            return False
        if condition.service_ranges is not None and not any(
            service.network_id == program.network_id and service.service_id == program.service_id
            for service in condition.service_ranges
        ):
            return False
        if condition.broadcast_type != 'All' and program.is_free != (condition.broadcast_type == 'FreeOnly'):
            return False
        if condition.genre_ranges:
            included = any(
                (requested['major'] == actual['major'] and
                 (requested['middle'] == 'すべて' or requested['middle'] == actual['middle']))
                for requested in condition.genre_ranges for actual in program.genres
            ) or (not program.genres and any(genre['major'] == 'ジャンルなし' for genre in condition.genre_ranges))
            if included == condition.is_exclude_genre_ranges:
                return False
        if condition.date_ranges:
            start_time = program.start_time.astimezone(JST)
            minute = (((start_time.weekday() + 1) % 7) * 24 + start_time.hour) * 60 + start_time.minute
            included = False
            for date in condition.date_ranges:
                start = (date.start_day_of_week * 24 + date.start_hour) * 60 + date.start_minute
                end = (date.end_day_of_week * 24 + date.end_hour) * 60 + date.end_minute
                if (start <= minute <= end if start < end else minute >= start or minute <= end):
                    included = True
            if included == condition.is_exclude_date_ranges:
                return False
        if condition.duration_range_min is not None and program.duration < condition.duration_range_min * 60:
            return False
        if condition.duration_range_max is not None and program.duration > condition.duration_range_max * 60:
            return False
        if not condition.keyword and not condition.exclude_keyword:
            return True
        fields = {
            'title': program.title,
            'event': '\r\n'.join([program.title, program.description, *program.detail.keys(), *program.detail.values()]),
            'genre': '\r\n'.join(f'{genre["major"]} - {genre["middle"]}' for genre in program.genres),
            'video': program.video_type or '',
            'audio': '\r\n'.join(filter(None, [program.primary_audio_type, program.secondary_audio_type])),
        }
        fields = {key: NormalizeSearchText(value) for key, value in fields.items()}
        target = fields['title' if condition.is_title_only else 'event']
        if condition.is_regex_search_enabled:
            include, exclude = self.patterns
            return (include is None or include.search(target) is not None) and (exclude is None or exclude.search(target) is None)
        if not condition.is_case_sensitive:
            fields = {key: value.casefold() for key, value in fields.items()}

        def Matches(keyword: str, fuzzy: bool = False) -> bool:
            field = 'title' if condition.is_title_only else 'event'
            for prefix in fields:
                if keyword.startswith(f':{prefix}:'):
                    field, keyword = prefix, keyword[len(prefix) + 2:]
                    break
            keyword = NormalizeSearchText(keyword)
            if not condition.is_case_sensitive:
                keyword = keyword.casefold()
            return bool(keyword) and (MatchesFuzzyKeyword(keyword, fields[field]) if fuzzy else keyword in fields[field])

        if any(Matches(keyword) for keyword in condition.exclude_keyword.split()):
            return False
        groups: list[list[str]] = [[]]
        for keyword in condition.keyword.split():
            if keyword == '|':
                groups.append([])
            else:
                groups[-1].append(keyword)
        return any(all(Matches(keyword, condition.is_fuzzy_search_enabled) for keyword in group) for group in groups)


async def SearchPrograms(condition: schemas.ProgramSearchCondition) -> list[schemas.Program]:
    matcher = ProgramMatcher(condition)
    if not condition.is_enabled:
        return []
    query = Program.filter(channel__is_watchable=True, end_time__gt=datetime.now(JST))
    if condition.service_ranges is not None:
        query = query.filter(channel_id__in=[
            f'NID{service.network_id}-SID{service.service_id:03d}' for service in condition.service_ranges
        ])
    if condition.duration_range_min is not None:
        query = query.filter(duration__gte=condition.duration_range_min * 60)
    if condition.duration_range_max is not None:
        query = query.filter(duration__lte=condition.duration_range_max * 60)
    if condition.broadcast_type != 'All':
        query = query.filter(is_free=condition.broadcast_type == 'FreeOnly')
    results: list[schemas.Program] = []
    async with in_transaction() as connection:
        program_ids = TypeAdapter(list[str]).validate_python(
            await query.using_db(connection).order_by('start_time', 'id').values_list('id', flat=True),
        )
        for offset in range(0, len(program_ids), 128):
            batch_ids = program_ids[offset:offset + 128]
            order = {program_id: index for index, program_id in enumerate(batch_ids)}
            rows = await Program.filter(id__in=batch_ids).using_db(connection).values()
            programs = [schemas.Program.model_validate(row) for row in rows]
            programs.sort(key=lambda program: order[program.id])
            results.extend(program for program in programs if matcher.matches(program))
            await asyncio.sleep(0)
    return results
