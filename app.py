import time
import json
import argparse
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)
STATE = []


def count_comments(comments):
    total = len(comments)
    for c in comments:
        if isinstance(c, dict):
            total += len(c.get("replies", []))
    return total


@app.route('/')
def index():
    return render_template('index.html', videos=STATE)


@app.route('/api/reset', methods=['POST'])
def reset_data():
    global STATE
    STATE = request.json

    for v in STATE:
        v['total_comment_count'] = count_comments(v['comments'])
        v.setdefault('is_liked', False)
        v.setdefault('likes', 0)
        v.setdefault('is_collected', False)
        v.setdefault('collects', 0)
    return jsonify({"status": "success"})


@app.route('/api/video/<int:vid>/like', methods=['POST'])
def toggle_like(vid):
    video = next((v for v in STATE if v['id'] == vid), None)
    if video:
        video['is_liked'] = not video['is_liked']
        video['likes'] += 1 if video['is_liked'] else -1
        return jsonify({
            "status": "success",
            "likes": video['likes'],
            "is_liked": video['is_liked'],
        })
    return jsonify({"status": "error"}), 404


@app.route('/api/video/<int:vid>/collect', methods=['POST'])
def toggle_collect(vid):
    video = next((v for v in STATE if v['id'] == vid), None)
    if video:
        video['is_collected'] = not video['is_collected']
        video['collects'] += 1 if video['is_collected'] else -1
        return jsonify({
            "status": "success",
            "collects": video['collects'],
            "is_collected": video['is_collected'],
        })
    return jsonify({"status": "error"}), 404


@app.route('/api/video/<int:vid>/comments', methods=['GET', 'POST'])
def handle_comments(vid):
    video = next((v for v in STATE if v['id'] == vid), None)
    if not video:
        return jsonify({"status": "error"}), 404
    if request.method == 'POST':
        data = request.json
        new_comment = {
            "id": int(time.time()),
            "user": "Agent_User",
            "text": data.get('text'),
            "replies": [],
        }
        video['comments'].append(new_comment)
    return jsonify({
        "comments": video['comments'],
        "count": count_comments(video['comments']),
    })


@app.route('/api/video/<int:vid>/reports', methods=['POST'])
def submit_report(vid):
    video = next((v for v in STATE if v['id'] == vid), None)
    if not video:
        return jsonify({"status": "error"}), 404
    data = request.json
    video['reports'].append({
        "category": data.get("category"),
        "reason": data.get("reason"),
        "timestamp": time.time(),
    })
    return jsonify({"status": "success"})


@app.route('/api/debug/state', methods=['GET'])
def get_state():
    return jsonify(STATE)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Short-video backend server')
    parser.add_argument('--port', type=int, default=5000, help='Server port (default 5000)')
    args = parser.parse_args()
    app.run(debug=True, port=args.port)
