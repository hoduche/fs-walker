import ast
import collections
import hashlib
import io
import json
import pathlib
import zipfile

BLOCK_SIZE = 65536  # ie 64 Ko
FILE_TYPE = 'FILE'
DIR_TYPE = 'DIR'


def crawl(path, exclusion=None):
    """
    Recursively crawls through a root directory to list its content.
    It manages two data structures:
    listing : a collections.defaultdict(set) whose keys are tuples (hash, type, size)
              and values are list of pathlib.Path
    tree    : a dictionary whose keys are pathlib.Path and values are tuples (hash, type, size)
    in both data structures, the type distinguishes files from directories

    :param path: path of the root directory to parse
    :type path: pathlib.Path

    :param exclusion: list of directories and files not to parse
    :type exclusion: list of str

    :return: root directory listing
    :rtype: collections.defaultdict(set) = {(hash, type, int): {pathlib.Path}}

    :return: root directory tree
    :rtype: dict = {pathlib.Path: (hash, type, int)}
    """
    if not exclusion:
        exclusion = []

    listing = collections.defaultdict(set)
    tree = dict()

    _recursive_crawl(path, listing, tree, exclusion)

    return listing, tree


def _recursive_crawl(path, listing, tree, exclusion):
    if path.is_dir():
        dir_content_size = 0
        dir_content_hash_list = []
        for each_child in path.iterdir():
            if each_child.name not in exclusion:
                _recursive_crawl(each_child, listing, tree, exclusion)
                dir_content_size += tree[each_child][2]
                dir_content_hash_list.append(tree[each_child][0])
        dir_content = '\n'.join(sorted(dir_content_hash_list))
        dir_content_hash = hashlib.md5(dir_content.encode()).hexdigest()
        dir_content_key = (dir_content_hash, DIR_TYPE, dir_content_size)
        listing[dir_content_key].add(path)
        tree[path] = dir_content_key

    elif path.is_file() and path.suffix == '.zip':
        dir_content_size = 0
        dir_content_hash_list = []
        with zipfile.ZipFile(path, 'r') as zfile:
            root_path = zipfile.Path(zfile)
            for each_child in root_path.iterdir():
                real_path = pathlib.Path(str(each_child))
                file_hasher = hashlib.md5()
                with each_child.open('r') as file_content:
                    content_stream = file_content.read(BLOCK_SIZE)
                    while len(content_stream) > 0:
                        file_hasher.update(content_stream)
                        content_stream = file_content.read(BLOCK_SIZE)
                file_content_hash = file_hasher.hexdigest()
                file_content_size = zfile.getinfo(each_child.name).file_size
                file_content_key = (file_content_hash, FILE_TYPE, file_content_size)
                listing[file_content_key].add(real_path)
                tree[real_path] = file_content_key
                dir_content_size += tree[real_path][2]
                dir_content_hash_list.append(tree[real_path][0])
        dir_content = '\n'.join(sorted(dir_content_hash_list))
        dir_content_hash = hashlib.md5(dir_content.encode()).hexdigest()
        dir_content_key = (dir_content_hash, DIR_TYPE, dir_content_size)
        listing[dir_content_key].add(path)
        tree[path] = dir_content_key

    elif path.is_file():
        file_hasher = hashlib.md5()
        with open(path, 'rb') as file_content:
            content_stream = file_content.read(BLOCK_SIZE)
            while len(content_stream) > 0:
                file_hasher.update(content_stream)
                content_stream = file_content.read(BLOCK_SIZE)
        file_content_hash = file_hasher.hexdigest()
        file_content_size = path.stat().st_size
        file_content_key = (file_content_hash, FILE_TYPE, file_content_size)
        listing[file_content_key].add(path)
        tree[path] = file_content_key


def dump_json_listing(listing, file_path):
    """
    :param: listing to serialize in json
    :rtype: collections.defaultdict(set) = {(hash, type, int): {pathlib.Path}}

    :param file_path: path to create the json serialized listing
    :type file_path: pathlib.Path
    """
    serializable_listing = {str(tuple_key): [str(path) for path in path_set]
                            for tuple_key, path_set in listing.items()}
    json_listing = json.dumps(serializable_listing)
    file_path.write_text(json_listing)


def load_json_listing(file_path):
    """
    :param file_path: path to an existing json serialized listing
    :type file_path: pathlib.Path

    :return: deserialized listing
    :rtype: collections.defaultdict(set) = {(hash, type, int): {pathlib.Path}}
    """
    json_listing = file_path.read_text()
    serializable_listing = json.loads(json_listing)
    dict_listing = {ast.literal_eval(tuple_key): {pathlib.Path(path) for path in path_list}
                    for tuple_key, path_list in serializable_listing.items()}
    listing = collections.defaultdict(set, dict_listing)
    return listing


def dump_json_tree(tree, file_path):
    """
    :param: tree to serialize in json
    :rtype: dict = {pathlib.Path: (hash, type, int)}

    :param file_path: path to create the json serialized tree
    :type file_path: pathlib.Path
    """
    serializable_tree = {str(path_key): tuple_value for path_key, tuple_value in tree.items()}
    json_tree = json.dumps(serializable_tree)
    file_path.write_text(json_tree)


def load_json_tree(file_path):
    """
    :param file_path: path to an existing json serialized tree
    :type file_path: pathlib.Path

    :return: deserialized tree
    :rtype: dict = {pathlib.Path: (hash, type, int)}
    """
    json_tree = file_path.read_text()
    serializable_tree = json.loads(json_tree)
    tree = {pathlib.Path(path_key): tuple(value) for path_key, value in serializable_tree.items()}
    return tree


def unify(listings, trees):
    tree = dict()  # = {pathlib.Path: (hash, type, int)}
    for each_tree in trees:
        for k, v in each_tree.items():
            if (not k in tree) or (tree[k][2] < v[2]):
                tree[k] = v
    listing = collections.defaultdict(set)  # = {(hash, type, int): {pathlib.Path}}
    for each_listing in listings:
        for k, v in each_listing.items():
            for each_v in v:
                if tree[each_v] == k:
                    listing[k].add(each_v)
    return listing, tree


def get_duplicates(listing):
    duplicates = {k: v for k, v in listing.items() if len(v) >= 2}
    size_gain = sum([k[2] * (len(v) - 1) for k, v in duplicates.items()])
    duplicates_sorted_by_size = {k: v for (k, v) in sorted(duplicates.items(),
                                                           key=lambda i: i[0][2],
                                                           reverse=True)}
    result = collections.defaultdict(set, duplicates_sorted_by_size)
    return result, size_gain


def get_non_included(listing, listing_ref):
    non_included = {k: v for k, v in listing.items() if k not in listing_ref}
    result = collections.defaultdict(set, non_included)
    return result


if __name__ == '__main__':
    desktop_path = pathlib.Path('C:/Users') / 'Henri-Olivier' / 'Desktop'
#    folder_path = pathlib.Path('M:/PhotosVideos')
#    listing, tree = crawl(folder_path)
#    duplicates = get_duplicates(listing)
#    dump_json_listing(duplicates, desktop_path / 'photos_duplicates.json')

#    duplicates = load_json_listing(desktop_path / 'photos_duplicates.json')
#    duplicates_sorted, size_gain = get_duplicates(duplicates)
#    dump_json_listing(duplicates_sorted, desktop_path / 'photos_duplicates_sorted.json')
#    print(f'you can gain {size_gain / 1E9:.2f} Gigabytes space')

    zip_path = desktop_path / 'blue.zip'
    with zipfile.ZipFile(zip_path, 'r') as zip_file:
        for file_name in zip_file.namelist():
#            print(str(desktop_path / 'blue.zip' / file_name))
            with zip_file.open(file_name) as file:
#                print(file.read())
#                print('--')
                pass
#    print('------------------')
    zip_path = desktop_path / 'blue.zip'
    print(zipfile.is_zipfile(str(zip_path)))
    with zipfile.ZipFile(zip_path, 'r') as zip_file:
        zip_file.printdir()
        root_path = zipfile.Path(zip_file)
        for each_path in root_path.iterdir():
            real_path = pathlib.Path(str(each_path))
            print(each_path)
            print(real_path)
            print(zipfile.is_zipfile(str(each_path)))
            print(zipfile.is_zipfile(str(real_path)))
            if real_path.suffix == '.zip':
                print(True)
                with each_path.open() as file:
                    with zipfile.ZipFile(io.BytesIO(file.read()), 'r') as nested_zip_file:
                        nested_zip_file.printdir()
            if each_path.is_file():
                print(zip_file.getinfo(each_path.name).file_size)
                with each_path.open() as file:
                    print(file.read())
                    print('--')
