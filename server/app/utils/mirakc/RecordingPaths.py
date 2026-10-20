from pathlib import PurePosixPath, PureWindowsPath

from fastapi import HTTPException

from app import schemas


ROOT = PurePosixPath('KonomiTV')


def RelativeFolder(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (path.is_absolute() or PureWindowsPath(value).drive or '\\' in value or
        '..' in value.split('/') or any(ord(character) < 32 or ord(character) == 127 for character in value)):
        raise ValueError('録画フォルダーはKonomiTV録画フォルダー以下の相対パスで指定してください。')
    return path


def EncodeRecordingFolder(folders: list[schemas.RecordingFolder]) -> PurePosixPath:
    if not folders:
        return ROOT
    if len(folders) != 1:
        raise HTTPException(422, 'mirakcの録画先にはフォルダーを1つだけ指定してください。')
    folder = folders[0]
    if folder.is_oneseg_separate_recording_folder:
        raise HTTPException(422, 'mirakcではワンセグの別フォルダー録画に対応していません。')
    if folder.recording_file_name_template not in (None, ''):
        raise HTTPException(422, 'mirakcでは録画ファイル名テンプレートに対応していません。')
    try:
        return ROOT / RelativeFolder(folder.recording_folder_path)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


def DecodeRecordingFolders(content_path: str) -> list[schemas.RecordingFolder]:
    try:
        path = RelativeFolder(content_path).relative_to(ROOT)
        if path == PurePosixPath('.'):
            raise ValueError('録画ファイル名がありません。')
    except ValueError as error:
        raise HTTPException(502, 'mirakcの録画パスがKonomiTV録画フォルダーの範囲外です。') from error
    if path.parent == PurePosixPath('.'):
        return []
    return [schemas.RecordingFolder(recording_folder_path=str(path.parent))]
