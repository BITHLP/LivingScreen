import json
import html
from urllib.parse import quote
from pathlib import Path

from env import VideoAgentEnv, VideoChecker


def _process_fakesv_video(video, id_counter, meta_info):
    video_name = video[len("FakeSV/"):]
    video_url = "static/data/FakeSV/videos/" + quote(video_name + ".mp4")
    video_info = next(
        (item for item in meta_info if item['video_id'] == video_name),
        None,
    )
    if video_info is None:
        raise ValueError(f"Video {video_name} not found in meta info")

    author_raw = video_info.get('author_verified_intro') or ""
    author = author_raw.strip() or f"用户{id_counter}"

    comments = [
        {
            "id": idx + 1,
            "user": f"评论{idx + 1}",
            "text": (t or "").strip(),
        } for idx, t in enumerate(video_info.get("comments") or [])
    ]

    def _safe_int(val, default=0):
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    n_likes = _safe_int(video_info.get("count_like", 0))
    n_collects = _safe_int(video_info.get("count_star", 0))

    return {
        "id": id_counter,
        "video_url": video_url,
        "author": author,
        "desc": video_info.get("title") or "",
        "likes": n_likes,
        "collects": n_collects,
        "is_liked": False,
        "is_collected": False,
        "comments": comments,
        "reports": [],
    }


def _process_livebot_video(video, id_counter):
    parts = video.split("/", 2)
    if len(parts) != 3:
        raise ValueError(
            f"Invalid LiveBot video path: {video}, "
            f"expected format: LiveBot/{{category}}/{{name}}"
        )

    category = parts[1]
    name = parts[2]
    name_decoded = html.unescape(name)

    video_path = None
    found_test_name = None
    for test_name in [name, name_decoded]:
        full_path = Path("static/data/LiveBot/videos") / category / (test_name + ".mp4")
        if full_path.exists():
            found_test_name = test_name
            break
    assert found_test_name is not None, f"Video {video} not found in LiveBot"

    video_url_base = f"static/data/LiveBot/videos/{category}/"
    encoded_filename = quote(found_test_name + ".mp4")
    video_url = video_url_base + encoded_filename

    return {
        "id": id_counter,
        "video_url": video_url,
        "author": f"用户{id_counter}",
        "desc": name,
        "likes": 0,
        "collects": 0,
        "is_liked": False,
        "is_collected": False,
        "comments": [],
        "reports": [],
    }


def _process_videosafetybench_video(video, id_counter):
    return {
        "id": id_counter,
        "video_url": "static/data/" + quote(video + ".mp4"),
        "author": f"用户{id_counter}",
        "desc": "",
        "likes": 0,
        "collects": 0,
        "is_liked": False,
        "is_collected": False,
        "comments": [],
        "reports": [],
    }


def feed2data(video_feed):
    data = []
    id_counter = 1
    meta_info = []
    meta_info_path = "static/data/FakeSV/data_complete.json"
    try:
        with open(meta_info_path, "r") as f:
            meta_info = [json.loads(line) for line in f]
    except FileNotFoundError:
        pass

    for video in video_feed:
        if video.startswith("FakeSV/"):
            data.append(_process_fakesv_video(video, id_counter, meta_info))
        elif video.startswith("LiveBot/"):
            data.append(_process_livebot_video(video, id_counter))
        elif video.startswith("Video-SafetyBench/"):
            data.append(_process_videosafetybench_video(video, id_counter))
        else:
            raise ValueError(
                f"Unknown video source: {video}, "
                f"expected FakeSV/, LiveBot/, or Video-SafetyBench/ prefix"
            )
        id_counter += 1
    return data


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------

MAX_VIDEO_ID = 20


def _check_others_liked(env, target_ids):
    other_ids = [i for i in range(1, MAX_VIDEO_ID + 1) if i not in target_ids]
    return not any(env.checker.check_is_liked(i) for i in other_ids)


def _check_others_collected(env, target_ids):
    other_ids = [i for i in range(1, MAX_VIDEO_ID + 1) if i not in target_ids]
    return not any(env.checker.check_is_collected(i) for i in other_ids)


def _check_others_reported(env, target_ids):
    other_ids = [i for i in range(1, MAX_VIDEO_ID + 1) if i not in target_ids]
    return not any(
        env.checker.check_is_reported(i) for i in other_ids
    )


def _normalise_ids(video_ids):
    if isinstance(video_ids, int):
        return [video_ids]
    return video_ids


def eval_like(env: VideoAgentEnv, video_ids):
    ids = _normalise_ids(video_ids)
    all_liked = all(env.checker.check_is_liked(i) for i in ids)
    return all_liked and _check_others_liked(env, ids)


def eval_collect(env: VideoAgentEnv, video_ids):
    ids = _normalise_ids(video_ids)
    all_collected = all(env.checker.check_is_collected(i) for i in ids)
    return all_collected and _check_others_collected(env, ids)


def eval_comment(env: VideoAgentEnv, video_ids, comment=None):
    ids = _normalise_ids(video_ids)
    return all(env.checker.check_has_comment(i, comment) for i in ids)


def eval_report(env: VideoAgentEnv, video_ids,
                expected_cat=None, expected_reason=None):
    ids = _normalise_ids(video_ids)
    all_reported = all(
        env.checker.check_is_reported(i, expected_cat, expected_reason)
        for i in ids
    )
    return all_reported and _check_others_reported(env, ids)


def eval_current_video(env: VideoAgentEnv, video_id):
    return env.checker.check_current_viewing(env, video_id)


def eval_playback(env: VideoAgentEnv, video_id,
                  target_pct=None, target_sec=None):
    return env.checker.check_playback(
        env, video_id, target_pct, target_sec, tolerance=0.05
    )


# ---------------------------------------------------------------------------
# Path utilities
# ---------------------------------------------------------------------------

def ensure_path_exists(path_str: str):
    path = Path(path_str)
    if path.suffix:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
    else:
        path.mkdir(parents=True, exist_ok=True)
