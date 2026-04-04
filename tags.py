# tags.py
import json
import os
import sys

def _get_tags_file():
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base, "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "tags.json")

TAGS_FILE = _get_tags_file()

DEFAULT_TAGS = ["work", "personal", "code", "other"]

def load_tags():
    if not os.path.exists(TAGS_FILE):
        with open(TAGS_FILE, "w") as f:
            json.dump(DEFAULT_TAGS, f)
        return DEFAULT_TAGS
    with open(TAGS_FILE, "r") as f:
        return json.load(f)

def save_tag(tag):
    tags = load_tags()
    if tag not in tags:
        tags.append(tag)
        with open(TAGS_FILE, "w") as f:
            json.dump(tags, f, indent=2)
    return tags

def delete_tag(tag):
    tags = load_tags()
    tags = [t for t in tags if t != tag]
    with open(TAGS_FILE, "w") as f:
        json.dump(tags, f, indent=2)
    import storage
    clips = storage.load_clips()
    for clip in clips:
        if clip.get("tag") == tag:
            clip["tag"] = None
    with open(storage.DATA_FILE, "w") as f:
        json.dump(clips, f, indent=2)
    return tags

def rename_tag(old_name, new_name):
    tag_list = load_tags()
    tag_list = [new_name if t == old_name else t for t in tag_list]
    with open(TAGS_FILE, "w") as f:
        json.dump(tag_list, f, indent=2)
    import storage
    clips = storage.load_clips()
    for clip in clips:
        if clip.get("tag") == old_name:
            clip["tag"] = new_name
    with open(storage.DATA_FILE, "w") as f:
        json.dump(clips, f, indent=2)
    return tag_list