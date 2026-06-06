import json


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "click",
            "description": "点击屏幕上的特定坐标点。",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 1000,
                        "description": "归一化 X 坐标",
                    },
                    "y": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 1000,
                        "description": "归一化 Y 坐标",
                    },
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swipe",
            "description": "在屏幕上从一个点滑动到另一个点。",
            "parameters": {
                "type": "object",
                "properties": {
                    "x1": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 1000,
                        "description": "起始点归一化 X 坐标",
                    },
                    "y1": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 1000,
                        "description": "起始点归一化 Y 坐标",
                    },
                    "x2": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 1000,
                        "description": "结束点归一化 X 坐标",
                    },
                    "y2": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 1000,
                        "description": "结束点归一化 Y 坐标",
                    },
                },
                "required": ["x1", "y1", "x2", "y2"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "等待指定的秒数，用于等待页面加载或视频播放。",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 60,
                        "description": "等待的秒数",
                    },
                },
                "required": ["seconds"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "watch",
            "description": "观看视频指定的秒数，期间会录制视频。",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 60,
                        "description": "观看的秒数",
                    },
                    "fps": {
                        "type": "number",
                        "minimum": 0.1,
                        "maximum": 30,
                        "default": 1,
                        "description": "视频帧率",
                    },
                },
                "required": ["seconds"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type",
            "description": "在当前激活的输入框中输入文本。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "要输入的字符串内容",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "answer",
            "description": "生成内容回答用户问题。要求仅回答选项（如“A”等），不包含任何解释。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "回答的字符串内容",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "当用户要求的任务已完全达成时调用此函数。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_point",
            "description": "在屏幕截图上标记一个点，用红色的靶心标记表示，用于确认位置是否与预期相符。",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 1000,
                        "description": "归一化 X 坐标",
                    },
                    "y": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 1000,
                        "description": "归一化 Y 坐标",
                    },
                },
                "required": ["x", "y"],
            },
        },
    },
]


SYSTEM_PROMPT = """你是一个专业的 GUI 操控智能体，专门负责在短视频平台中进行交互。你的任务是根据用户的长期目标，通过观察屏幕截图或视频流输出精确指令。

你的输入图像来自于一个典型的短视频流环境界面的截图。该短视频流的长度是有限的，如果连续多次向上滑动后界面可能不再更新内容。请使用**相对**图像坐标，将输入图像的宽高视为 0 到 1000 的归一化坐标系：图像左上角为 <point>0 0</point>，右上角为 <point>1000 0</point>，右下角为 <point>1000 1000</point>。你可以进行点击视频以暂停/继续、点击进度条特定位置跳转、从下向上拖拽进入下个视频和从上向下拖拽回到上个视频等操作。

每次响应中的推理思考后，你**必须**先输出一个简洁的总结，内容放在普通文本回复中，以<summary></summary>包裹，总结当前的状态、已完成的步骤、以及即将调用的工具计划，以便在后续对话中参考。这个总结将被保留在对话历史中。接着，你应调用工具进行操作，并在任务圆满完成时调用 `finish` 工具。"""


SYSTEM_PROMPT_NO_SUMMARY = """你是一个专业的 GUI 操控智能体，专门负责在短视频平台中进行交互。你的任务是根据用户的长期目标，通过观察屏幕截图或视频流输出精确指令。

你的输入图像来自于一个典型的短视频流环境界面的截图。该短视频流的长度是有限的，如果连续多次向上滑动后界面可能不再更新内容。请使用**相对**图像坐标，将输入图像的宽高视为 0 到 1000 的归一化坐标系：图像左上角为 <point>0 0</point>，右上角为 <point>1000 0</point>，右下角为 <point>1000 1000</point>。你可以进行点击视频以暂停/继续、点击进度条特定位置跳转、从下向上拖拽进入下个视频和从上向下拖拽回到上个视频等操作。

每次响应中的推理思考后，你应调用工具进行操作，并在任务圆满完成时调用 `finish` 工具。"""


OBSERVATION_LESS_PROMPT = "请节约你的观察开销。除非确有必要，不要调用 `watch`，优先使用 `wait` 或直接跳过视频。当你犹豫是否要继续看时，选择前进而非继续观察。"


OBSERVATION_MORE_PROMPT = "请充分地进行观察。只要一个视频与任务可能相关，就调用 `watch` 仔细查看，且倾向于观察更长的片段而非更短的片段。在详细查看过与答案相关的视频之前，不要急于作答。"


OBSERVATION_HUMAN_PROMPT = "请模仿专业、专注的人类用户的方式进行观察。对每一个视频，先简短查看几秒，以判断它是否与任务相关；只有当这一次初步查看表明该视频对回答任务有实质帮助时，才进一步使用 `watch` 短时间查看；如果发现可能有更多未掌握的相关内容，再尝试观看更靠后的部分。"


class GUIAgent:

    def __init__(self, model, use_video=True, keep_reasoning=True,
                 use_summary=False, keep_tool_rounds=1,
                 observation_mode='default'):
        self.model = model
        self.history = None
        self.use_video = use_video
        self.keep_reasoning = keep_reasoning
        self.use_summary = use_summary
        self.system_prompt = SYSTEM_PROMPT if use_summary else SYSTEM_PROMPT_NO_SUMMARY

        if observation_mode == 'less':
            self.system_prompt += "\n" + OBSERVATION_LESS_PROMPT
        elif observation_mode == 'more':
            self.system_prompt += "\n" + OBSERVATION_MORE_PROMPT
        elif observation_mode == 'human':
            self.system_prompt += "\n" + OBSERVATION_HUMAN_PROMPT

        self.keep_tool_rounds = keep_tool_rounds

    def _generate_auto_summary(self, tool_calls_dict):
        if not tool_calls_dict:
            return "<summary>没有需要执行的操作。</summary>"

        tool_descriptions = []
        for tc in tool_calls_dict:
            func_name = tc['function']['name']
            args = dict(json.loads(tc['function']['arguments']))

            if func_name == 'click':
                tool_descriptions.append(
                    f"点击坐标({args.get('x', 0)}, {args.get('y', 0)})")
            elif func_name == 'swipe':
                tool_descriptions.append(
                    f"从({args.get('x1', 0)}, {args.get('y1', 0)})"
                    f"滑动到({args.get('x2', 0)}, {args.get('y2', 0)})")
            elif func_name == 'type':
                tool_descriptions.append(f"输入文本：{args.get('text', '')}")
            elif func_name == 'wait':
                tool_descriptions.append(f"等待{args.get('seconds', 0)}秒")
            elif func_name == 'watch':
                tool_descriptions.append(f"观看视频{args.get('seconds', 0)}秒")
            elif func_name == 'answer':
                tool_descriptions.append(f"回答：{args.get('text', '')}")
            elif func_name == 'finish':
                tool_descriptions.append("任务完成")
            elif func_name == 'mark_point':
                tool_descriptions.append(
                    f"在坐标({args.get('x', 0)}, {args.get('y', 0)})标记一个点")

        return f"<summary>计划执行以下操作：{'，'.join(tool_descriptions)}。</summary>"

    def reset_goal(self, instruction, image):
        self.history = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image}"},
                    },
                    {"type": "text", "text": instruction},
                ],
            },
        ]

    def step(self):
        filtered_messages = self._filter_messages()
        res = self.model.chat(messages=filtered_messages, tools=TOOLS)

        reasoning_details = getattr(res, "reasoning_details", None)
        reasoning_content = getattr(res, "reasoning_content", "") or ""
        content = res.content if res.content else ""
        role = res.role if res.role else ""
        tool_calls = res.tool_calls if res.tool_calls else []
        tool_calls_dict = [
            tool_call.model_dump() for tool_call in tool_calls
        ] if tool_calls else []

        if self.use_summary:
            if tool_calls_dict and not content:
                if not reasoning_content:
                    content = self._generate_auto_summary(tool_calls_dict)
                else:
                    content = reasoning_content
            content = content.strip(' \n')
            if not content.startswith("<summary>") or not content.endswith("</summary>"):
                content = f"<summary>{content}</summary>"

        log = {
            "role": role,
            "content": content,
            "tool_calls": tool_calls_dict,
        }
        if reasoning_content:
            log["reasoning_content"] = reasoning_content
        if reasoning_details:
            log["reasoning_details"] = reasoning_details
        self.history.append(log)

        return tool_calls

    def _filter_messages(self):
        def process_message(msg, omit_tool_media=False):
            processed = msg.copy()
            if not self.keep_reasoning and "reasoning_content" in processed:
                del processed["reasoning_content"]
            if omit_tool_media and processed.get("role") == "tool" and "content" in processed:
                processed_content = []
                for item in processed["content"]:
                    if isinstance(item, dict) and item.get("type") == "image_url":
                        processed_content.append({
                            "type": "text",
                            "text": "[Image data omitted to save tokens]",
                        })
                    elif isinstance(item, dict) and item.get("type") == "video_url":
                        processed_content.append({
                            "type": "text",
                            "text": "[Video data omitted to save tokens]",
                        })
                    else:
                        processed_content.append(item)
                processed["content"] = processed_content
            return processed

        if not self.history:
            return []

        filtered = self.history[:2]
        if len(self.history) <= 2:
            return [process_message(msg) for msg in filtered]

        tool_indices = [
            i for i, msg in enumerate(self.history)
            if msg.get("role") == "tool"
        ]
        if len(tool_indices) <= self.keep_tool_rounds:
            filtered.extend(process_message(msg) for msg in self.history[2:])
        else:
            omitted_indices = set(tool_indices[:-self.keep_tool_rounds])
            for i, msg in enumerate(self.history[2:], 2):
                filtered.append(
                    process_message(msg, omit_tool_media=(i in omitted_indices))
                )

        return filtered

    def observe(self, observation_type, observation, tool_call_id):
        content = []

        if observation_type == 'video':
            content.append({"type": "text", "text": "页面录屏如下。"})
            content.append({
                "type": "video_url",
                "video_url": {"url": f"data:video/mp4;base64,{observation}"},
            })
        elif observation_type == 'frames':
            content.append({"type": "text", "text": "页面录屏的截图如下。"})
            for frame in observation:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{frame}"},
                })
        elif observation_type == 'image':
            content.append({"type": "text", "text": "这是执行上一步动作后的屏幕截图。"})
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{observation}"},
            })
        elif observation_type == 'text':
            content.append({"type": "text", "text": observation})
        else:
            raise ValueError(f"Unknown observation type: {observation_type}")

        self.history.append({
            "role": "tool",
            "content": content,
            "tool_call_id": tool_call_id,
        })

    def add_tool_responses(self, tool_calls, results):
        if len(tool_calls) != len(results):
            raise ValueError("tool_calls and results must have the same length")
        if len(tool_calls) == 0:
            self.history.append({
                "role": "user",
                "content": [{"type": "text", "text": "无工具调用。请调用工具进行操作。"}],
            })
        for idx, tool_call in enumerate(tool_calls):
            if idx < len(results) and results[idx] is not None:
                result, observation_type = results[idx]
                if result is not None:
                    self.observe(observation_type, result, tool_call.id)
                else:
                    self.history.append({
                        "role": "tool",
                        "content": [{"type": "text", "text": "Successfully executed tool."}],
                        "tool_call_id": tool_call.id,
                    })
            else:
                self.history.append({
                    "role": "tool",
                    "content": [{"type": "text", "text": "Successfully executed tool."}],
                    "tool_call_id": tool_call.id,
                })
