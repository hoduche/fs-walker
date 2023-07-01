import datetime
import enum
import os
import os.path
import pathlib
import shutil
import time
import zipfile


DATE_FORMAT = '%Y_%m_%d_%H_%M_%S'


class PathType(str, enum.Enum):
    FILE = 'FILE'
    DIR = 'DIR'


def get_path_type(path):
    if path.is_file():
        return PathType.FILE
    elif path.is_dir():
        return PathType.DIR
    else:
        assert "Oups"  # todo check if pythonic


def is_compressed_file(path):
    return path.is_file() and path.suffix in ['.zip', '.tar', '.gztar',
                                              '.bztar', '.xztar']


def build_relative_path(absolute_path, start_path):
    return pathlib.Path(os.path.relpath(str(absolute_path), start=start_path))


def add_suffix(file_path, suffix):
    return file_path.rename(file_path.with_stem(file_path.stem + suffix))


def build_datetime_tag(datetime_object):
    return datetime_object.strftime(DATE_FORMAT)


def build_current_datetime_tag():
    return build_datetime_tag(datetime.datetime.now())


def read_datetime_tag(datetime_string):
    return datetime.datetime.strptime(datetime_string, DATE_FORMAT)


def natural_size(num, unit='B'):
    for prefix in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(num) < 1024.0:
            result = f'{num:.1f} {prefix}{unit}'
            return result
        num /= 1024.0
    result = f'{num:.1f} Yi{unit}'
    return result


def unpack_archive_and_restore_mtime(path, extract_dir):
    shutil.unpack_archive(path, extract_dir=extract_dir)
    _restore_mtime_after_unpack(path, extract_dir=extract_dir)


def _restore_mtime_after_unpack(archive, extract_dir):
    archive_mtime = archive.stat().st_mtime
    os.utime(extract_dir, (archive_mtime, archive_mtime))
    info_map = {f.filename: f.date_time
                for f in zipfile.ZipFile(archive, 'r').infolist()}
    for file in extract_dir.rglob("*"):
        if file.name in info_map:
            # still need to adjust the dt o/w item will have the current dt
            mtime = time.mktime(info_map[file.name] + (0, 0, -1))
        else:
            mtime = archive_mtime
        os.utime(file, (mtime, mtime))
