import os
import json
import base64
import socket
import argparse
import threading
import subprocess
import time
import random
from queue import Queue

from tqdm import tqdm

import utils
from llms import *  # noqa: F401,F403  (globals() lookup by model_name)
from agent import GUIAgent, TOOLS
from env import VideoAgentEnv
from utils import feed2data, ensure_path_exists


# ---------------------------------------------------------------------------
# Tool-call validation
# ---------------------------------------------------------------------------

def validate_tool_args(func_name, args):
    """校验工具调用的参数类型与必填字段。

    Returns:
        (is_valid, error_message)
    """
    tool_def = next(
        (t for t in TOOLS if t['function']['name'] == func_name), None,
    )
    if not tool_def:
        return False, f"未知的工具函数: {func_name}"

    params = tool_def['function']['parameters']['properties']
    required = tool_def['function']['parameters'].get('required', [])

    for param_name in required:
        if param_name not in args:
            return False, f"缺少必需参数: {param_name}"

    for param_name, param_value in args.items():
        if param_name not in params:
            continue

        param_def = params[param_name]
        param_type = param_def['type']
        error_msg = ""

        if param_type == 'integer':
            if not isinstance(param_value, int):
                error_msg = (
                    f"参数 {param_name} 应该是整数类型，"
                    f"但实际是 {type(param_value).__name__}"
                )
        elif param_type == 'number':
            if not isinstance(param_value, (int, float)):
                error_msg = (
                    f"参数 {param_name} 应该是数字类型，"
                    f"但实际是 {type(param_value).__name__}"
                )
        elif param_type == 'string':
            if not isinstance(param_value, str):
                error_msg = (
                    f"参数 {param_name} 应该是字符串类型，"
                    f"但实际是 {type(param_value).__name__}"
                )

        # 额外对 integer / number 做范围校验
        if not error_msg and param_type in ('integer', 'number'):
            if 'minimum' in param_def and param_value < param_def['minimum']:
                error_msg = (
                    f"参数 {param_name} 的值 {param_value} "
                    f"小于最小值 {param_def['minimum']}"
                )
            elif 'maximum' in param_def and param_value > param_def['maximum']:
                error_msg = (
                    f"参数 {param_name} 的值 {param_value} "
                    f"大于最大值 {param_def['maximum']}"
                )

        if error_msg:
            return False, error_msg

    return True, ""


# ---------------------------------------------------------------------------
# Agent task runner
# ---------------------------------------------------------------------------

def run_task(env, agent, use_video=True, max_steps=10, progress_callback=None):
    finished = False
    feedbacks = [{"type": "image", "content": env.get_screenshot()}]

    for i in range(max_steps):
        tool_calls = agent.step()
        results = []

        for tool_call in tool_calls:
            func_name = tool_call.function.name
            if progress_callback:
                progress_callback(step=i + 1, func_name=func_name)

            # 解析参数
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError as e:
                results.append((f"JSON解析错误: {str(e)}", 'text'))
                break

            # 类型检查
            is_valid, error_msg = validate_tool_args(func_name, args)
            if not is_valid:
                results.append((error_msg, 'text'))
                break

            # 分发到对应的环境动作（坐标归一化到 env 尺寸）
            if func_name == "click":
                result = env.click_at(
                    args['x'] / 1000.0 * env.width,
                    args['y'] / 1000.0 * env.height,
                )
                observation_type = 'image'
            elif func_name == "swipe":
                result = env.swipe(
                    args['x1'] / 1000.0 * env.width,
                    args['y1'] / 1000.0 * env.height,
                    args['x2'] / 1000.0 * env.width,
                    args['y2'] / 1000.0 * env.height,
                )
                observation_type = 'image'
            elif func_name == 'mark_point':
                result = env.mark_point(
                    args['x'] / 1000.0 * env.width,
                    args['y'] / 1000.0 * env.height,
                )
                observation_type = 'image'
            elif func_name == "type":
                result = env.type_text(args['text'])
                observation_type = 'image'
            elif func_name == "wait":
                result = env.wait(args['seconds'])
                observation_type = 'image'
            elif func_name == "watch":
                fps = args.get('fps', 1)
                result = env.watch(args['seconds'], fps, use_video=use_video)
                observation_type = 'video' if use_video else 'frames'
            elif func_name == "finish":
                finished = True
                result = None
                observation_type = 'image'
            elif func_name == "answer":
                result = None
                observation_type = 'text'
            else:
                result = None
                observation_type = 'text'

            results.append((result, observation_type))

        # 将本轮工具调用的返回写回 agent 的对话历史
        agent.add_tool_responses(tool_calls, results)

        # 只把最后一个 tool_call 的结果放入 feedbacks（供日志保存用）
        if results and results[-1] and results[-1][0] is not None:
            last_result, last_observation_type = results[-1]
            feedbacks.append({
                "type": last_observation_type,
                "content": last_result,
            })

        if finished:
            break

    # 把 agent.history 里体积大的图片/视频内容去掉，以便保存为小体积 JSON
    history = []
    for item in agent.history:
        new_item = item.copy()
        if isinstance(new_item["content"], list):
            new_item["content"] = [
                c for c in new_item["content"]
                if c["type"] not in ("image_url", "video_url")
            ]
        history.append(new_item)

    return feedbacks, history


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def eval_task(env, history, eval_type, eval_config):

    def eval_label(env, gt_answer, history):
        for message in history:
            if "tool_calls" in message and message["tool_calls"]:
                for tool_call in message["tool_calls"]:
                    if tool_call["function"]["name"] == "answer":
                        args = json.loads(tool_call["function"]["arguments"])
                        answer_text = args.get("text", "")
                        return 1.0 if answer_text.strip() == gt_answer.strip() else 0.0
        return 0.0

    def eval_platform(env, eval_config):
        for eval_item in eval_config:
            eval_func_name = eval_item["func"]
            eval_func = getattr(utils, eval_func_name)
            eval_args = eval_item["args"]
            result = eval_func(env, **eval_args)
            if not result:
                return 0.0
        return 1.0

    if eval_type == "platform":
        return eval_platform(env, eval_config)
    elif eval_type == "label":
        return eval_label(env, eval_config[0]["answer"], history)
    else:
        raise ValueError(f"not supported eval_type: {eval_type}")


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

def save_feedback(feedback, save_dir, step_idx):
    if feedback['type'] == 'video':
        video_path = os.path.join(save_dir, f'step_{step_idx}.mp4')
        with open(video_path, 'wb') as f:
            f.write(base64.b64decode(feedback['content']))
    elif feedback['type'] == 'frames':
        for frame_idx, frame in enumerate(feedback['content']):
            img_path = os.path.join(
                save_dir, f'step_{step_idx}_frame_{frame_idx}.png',
            )
            with open(img_path, 'wb') as f:
                f.write(base64.b64decode(frame))
    elif feedback['type'] == 'image':
        img_path = os.path.join(save_dir, f'step_{step_idx}.png')
        with open(img_path, 'wb') as f:
            f.write(base64.b64decode(feedback['content']))
    elif feedback['type'] == 'text':
        pass
    else:
        raise ValueError(f"not supported feedback type: {feedback['type']}")


def check_port_available(port):
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        return sock.connect_ex(('127.0.0.1', port)) != 0
    except Exception:
        return True
    finally:
        if sock:
            sock.close()


def start_backend_server(port):
    process = subprocess.Popen(
        ['python', 'app.py', '--port', str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(2)
    return process


# ---------------------------------------------------------------------------
# Worker (runs inside a worker thread)
# ---------------------------------------------------------------------------

def worker(task_queue, result_queue, thread_id, base_port,
           use_video, keep_reasoning, use_summary, keep_tool_rounds,
           max_steps, log_path, category, model_name, observation_mode):
    port = base_port + thread_id
    backend_process = None
    try:
        backend_process = start_backend_server(port)
        model_class = globals().get(model_name)
        if not model_class:
            raise ValueError(f"未知模型: {model_name}")
        llm = model_class()

        while True:
            try:
                item = task_queue.get_nowait()
            except Exception:
                break

            task_id = item["task_id"]
            save_dir = f"{log_path}/{task_id}"
            ensure_path_exists(save_dir)
            save_path = f"{save_dir}/log.json"

            if os.path.exists(save_path):
                result_queue.put((task_id, None, "已跳过"))
                task_queue.task_done()
                continue

            try:
                env = VideoAgentEnv(
                    data=feed2data(item["video_feed"]), port=port,
                )
                agent = GUIAgent(
                    llm,
                    use_video=use_video,
                    keep_reasoning=keep_reasoning,
                    use_summary=use_summary,
                    keep_tool_rounds=keep_tool_rounds,
                    observation_mode=observation_mode,
                )
                agent.reset_goal(item["instruction"], env.get_screenshot())

                feedbacks, history = run_task(
                    env, agent, use_video=use_video, max_steps=max_steps,
                )
                result = eval_task(
                    env, history, item["eval_type"], item["eval_config"],
                )

                log = {
                    "instruction": item["instruction"],
                    "history": history,
                    "result": result,
                }
                with open(save_path, "w") as f:
                    json.dump(log, f, ensure_ascii=False, indent=4)

                for step_idx, step_feedback in enumerate(feedbacks):
                    save_feedback(step_feedback, save_dir, step_idx)

                env.close()
                result_queue.put((task_id, result, "完成"))
            except Exception as e:
                error_msg = f"错误: {str(e)}"
                print(f"\n❌ 任务 {task_id} 失败: {error_msg}")
                result_queue.put((task_id, None, error_msg))

            task_queue.task_done()

    finally:
        if backend_process:
            backend_process.terminate()
            backend_process.wait()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='LivingScreen benchmark multi-threaded evaluation',
    )
    parser.add_argument(
        '-t', '--category', type=str, default='gui_action',
        help='任务类别，默认为 gui_action',
    )
    parser.add_argument(
        '--logs', type=str, default='',
        help='日志目录，默认与 --category 同目录',
    )
    parser.add_argument(
        '--model', type=str, default='DoubaoSeed18',
        help='选择模型，默认为 DoubaoSeed18',
    )
    parser.add_argument(
        '--no-video', action='store_true', help='不使用视频模式',
    )
    parser.add_argument(
        '--base-port', type=int, default=5000,
        help='起始后端服务器端口，默认 5000',
    )
    parser.add_argument(
        '--no-keep-reasoning', action='store_true',
        help='不保留推理内容',
    )
    parser.add_argument(
        '--use-summary', action='store_true', help='使用总结',
    )
    parser.add_argument(
        '--keep-tool-rounds', type=int, default=1,
        help='保留的工具调用轮数',
    )
    parser.add_argument(
        '--max-steps', type=int, default=10,
        help='最大步数，默认 10',
    )
    parser.add_argument(
        '--threads', type=int, default=4, help='并发线程数，默认 4',
    )
    parser.add_argument(
        '--sample-n', type=int, default=None,
        help='随机采样 n 个任务进行测试',
    )
    parser.add_argument(
        '--eval-only', action='store_true',
        help='不运行，只进行 evaluation（统计已有结果）',
    )
    parser.add_argument(
        '--observation-mode', type=str, default='default',
        choices=['default', 'less', 'more', 'human'], help='观察模式',
    )
    args = parser.parse_args()

    category = args.category
    model_name = args.model
    logs = args.logs if args.logs else category
    use_video = not args.no_video
    keep_reasoning = not args.no_keep_reasoning
    use_summary = args.use_summary

    assert not (use_summary and keep_reasoning), \
        "使用总结时，不能保留推理内容"

    keep_tool_rounds = args.keep_tool_rounds
    max_steps = args.max_steps
    num_threads = args.threads
    base_port = args.base_port
    observation_mode = args.observation_mode

    task_path = f"data/{category}.json"
    assert os.path.exists(task_path), f"任务文件不存在: {task_path}"

    log_path = f"logs/{model_name}/{logs}"
    ensure_path_exists(log_path)

    with open(task_path, "r") as f:
        data = json.load(f)

    if args.sample_n is not None and args.sample_n > 0:
        if args.sample_n < len(data):
            data = random.sample(data, args.sample_n)
            print(f"已随机采样 {args.sample_n} 个任务进行测试")
        else:
            print(
                f"请求采样的数量 ({args.sample_n}) 大于等于总任务数 "
                f"({len(data)})，将使用所有任务"
            )

    if not args.eval_only:
        task_queue = Queue()
        result_queue = Queue()

        for item in data:
            task_queue.put(item)

        print(
            f"开始多线程测试，任务数: {len(data)}, "
            f"线程数: {num_threads}"
        )

        occupied_ports = []
        for i in range(num_threads):
            port = base_port + i
            if not check_port_available(port):
                occupied_ports.append(port)

        if occupied_ports:
            print(
                f"错误：以下端口已被占用: "
                f"{', '.join(map(str, occupied_ports))}"
            )
            print("请使用 --base-port 参数更改起始端口或关闭占用端口的程序")
            import sys
            sys.exit(1)

        print(
            f"端口检查通过，将使用端口: "
            f"{', '.join(map(str, [base_port + i for i in range(num_threads)]))}"
        )

        threads = []
        for i in range(num_threads):
            t = threading.Thread(
                target=worker,
                args=(
                    task_queue, result_queue, i, base_port,
                    use_video, keep_reasoning, use_summary,
                    keep_tool_rounds, max_steps, log_path,
                    category, model_name, observation_mode,
                ),
            )
            t.start()
            threads.append(t)

        pbar = tqdm(total=len(data))
        completed = 0
        while completed < len(data):
            task_id, result, status = result_queue.get()
            completed += 1
            pbar.set_description(f"任务: {task_id} | {status}")
            pbar.update(1)

        for t in threads:
            t.join()

        pbar.close()
    else:
        print("开启了 --eval-only 模式，跳过运行阶段，直接统计已有结果...")

    sum_score = 0.0
    task_scores = {}
    valid_count = 0

    for item in tqdm(data, desc="统计结果"):
        task_id = item["task_id"]
        save_path = f"{log_path}/{task_id}/log.json"

        if not os.path.exists(save_path):
            continue

        with open(save_path, "r") as f:
            log = json.load(f)

        if log["result"] is not None:
            sum_score += log["result"]
            valid_count += 1

            task_name = "_".join(task_id.split("_")[:-1])
            if task_name not in task_scores:
                task_scores[task_name] = []
            task_scores[task_name].append(log["result"])

    if valid_count > 0:
        avg_score_valid = sum_score / valid_count
        avg_score = sum_score / len(data)
        print(
            f"\n任务 '{category}' 平均分数: {avg_score:.4f} "
            f"有效分数: {avg_score_valid:.4f} "
            f"(有效任务: {valid_count}/{len(data)})"
        )
    else:
        print("\n没有有效的测试结果")

    if task_scores:
        print("\n各子任务平均分数:")
        for task_name, scores in task_scores.items():
            task_avg = sum(scores) / len(scores)
            print(
                f"{task_name}: {task_avg:.4f} "
                f"(共{len(scores)}个任务，总得分 {sum(scores)})",
            )
