from typing import Iterator, List, Tuple, Dict, Any, Union, Optional
from _decimal import Context, getcontext
from nodes import PreviewImage, SaveImage, NODE_CLASS_MAPPINGS as ALL_NODE_CLASS_MAPPINGS
from ..libs.utils import AlwaysEqualProxy, ByPassTypeTuple, cleanGPUUsedForce, compare_revision
from datetime import datetime
import json

try: # flow
    from comfy_execution.graph_utils import GraphBuilder, is_link
except:
    GraphBuilder = None

import logging
logger = logging.getLogger('comfyui_play_traversal_logger')
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()

logger.addHandler(handler)


CATEGORY = "Play Traversal (Video)"


DEFAULT_FLOW_NUM = 2
MAX_FLOW_NUM = 5

any_type = AlwaysEqualProxy("*")

# #############################################################################
class fot_Play:

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "vae": ("VAE",),
                "title": ("STRING", {"default": "Play title"}),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff, "control_after_generate": True, "tooltip": "The random seed used for creating the noise."}),
                "filename_base": ("STRING", {"default": "fot_test_play"}),
                # TODO how to limit fps to just a well known list
                "fps":  ("FLOAT", {"default": 20, "min": 1, "max": 100000, "step": 1}),
                "width":  ("INT", {"default": 480, "min": 1, "max": 100000, "step": 8}),
                "height":  ("INT", {"default": 832, "min": 1, "max": 100000, "step": 8}),
                "frames_count_per_batch":  ("INT", {"default": 41, "min": 1, "max": 100000, "step": 1}),
            },
            "optional": {
                "scene_%d" % i: ("SCENE",) for i in range(1, 3)
            },
            "hidden": {
                "scene_0": ("SCENE",),
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
                "unique_id": "UNIQUE_ID"
            }
        }

    RETURN_TYPES = ("FLOW_CONTROL", "MODEL", "VAE", "PLAY", "SCENE", "SCENE_BEAT", "BATCH",)
    RETURN_NAMES = ("control", "model", "vae", "play_current", "scene_current", "beat_current", "batch_current",)
    FUNCTION = "play_start"

    CATEGORY = CATEGORY

    def play_start(self, model, vae, title, positive, negative, seed, filename_base, fps, width, height,
                   frames_count_per_batch, scene_0=None, prompt=None, extra_pnginfo=None, unique_id=None,
                   **kwargs):

        play = {
            "model": model,
            "vae": vae,
            "title": title,
            "filename_base": filename_base,
            "fps": fps,
            "width": width,
            "height": height,
            "frames_count_per_batch": frames_count_per_batch,
            "positive": positive,
            "negative": negative,
            "seed": seed,
        }

        scenes = [kwargs.get("scene_%d" % i, None) for i in range(1, 3)]
        
        # ignoring trailing Nuns
        while scenes and scenes[-1] is None:
            scenes.pop()
        # need at least one remaining
        if len(scenes) == 0:
            raise ValueError("At least one scenes item is required")
        # Check for gaps (no Nuns in the middle)
        if None in scenes:
            raise ValueError("Found gap in scenes, please defragment!")

        logging.info(" == collecting time")

        duration_secs_play = 0
        index_play = 0
        for scene in scenes:
            scene["filename_base"] = filename_base + "_" + scene["filename_part"]

            scene_beats_list = scene.get("scene_beats", [])
            frames_count_scene = 0
            for scene_beats in scene_beats_list:
                scene_beats["filename_base"] = scene["filename_base"] + "_" + scene_beats["filename_part"]
                duration_secs_play += scene_beats["duration_secs"]
                scene_beats["frames_count"] = int(fps * scene_beats["duration_secs"])
                batch_count = scene_beats["frames_count"] % frames_count_per_batch
                remaining_count = scene_beats["frames_count"]
                last_frame = 0
                for i in range(0, batch_count):
                    batch = {
                        "index": i,
                        "index_play": index_play,
                        "filename": scene_beats["filename_base"] + "_" + str(i),
                        "frames_count": frames_count_per_batch,
                    }
                    index_play += 1
                    batch["frames_first"] = last_frame + i * frames_count_per_batch + 1
                    last_frame = batch["frames_first"] + frames_count_per_batch - 1
                    batch["frames_last"] = last_frame

                    batches = scene_beats.get("batches", []) # Use square brackets
                    batches.append(batch)
                    remaining_count = remaining_count - frames_count_per_batch
                if remaining_count > 0:
                    i = batch_count
                    batch = {
                        "index": i,
                        "index_play": index_play,
                        "filename": scene_beats["filename_base"] + "_" + str(i),
                        "frames_count": remaining_count,
                    }
                    index_play += 1
                    batch["frames_first"] = last_frame + i * frames_count_per_batch + 1
                    last_frame = batch["frames_first"] + remaining_count - 1
                    batch["frames_last"] = last_frame
                    batches = scene_beats.get("batches", []) # Use square brackets
                    batches.append(batch)

                frames_count_scene += scene_beats["frames_count"]
            scene["frames_count"] = frames_count_scene

        frames_count_total = int(fps * duration_secs_play)

        play["duration_secs"] = duration_secs_play
        play["frames_count"] = frames_count_total
        play["scenes"] = scenes

        # tmp init test before loop impl
        scene_current = scenes[0]# first scene
        beat_current = scene_current["scene_beats"][0] # first beat
        batch_current = beat_current["batches"][0] # first batch

        return (model, vae, play, scene_current, beat_current, batch_current,)

# this is a modified comfyui-easy-use:whileLoopStart
class fot_whileLoopStart:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        inputs = {
            "required": {
                "data": (any_type,),


                
            },
            "optional": {
            },
            "hidden": {
                "do_continue": ("BOOLEAN", {"default": True}),
            }
        }
        return inputs

    RETURN_TYPES = tuple(["FLOW_CONTROL", any_type]) # ByPassTypeTuple(tuple(["FLOW_CONTROL"] + [any_type] * MAX_FLOW_NUM))
    RETURN_NAMES = tuple(["flow", "data"]) # ByPassTypeTuple(tuple(["flow"] + ["value%d" % i for i in range(MAX_FLOW_NUM)]))
    FUNCTION = "while_loop_open"

    CATEGORY = CATEGORY

    def while_loop_open(self, data, do_continue=True, **kwargs):
        print("### while_loop_open")
        print(f"* do_continue = {do_continue}")
        print("* data =")
        print(data)
        print("\n")

        print("### END while_loop_open")
        return tuple(["stub", data])

# #############################################################################
class fot_PlayData:

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
            },
            "optional": {
                "play":  ("PLAY",),
            },
            "hidden": {
            }
        }

    RETURN_TYPES = ("MODEL","VAE", "STRING", "FLOAT", "INT", "INT", "INT", "INT", "CONDITIONING", "CONDITIONING", "SEED", "SCENE",)
    RETURN_NAMES = ("model", "vae", "title", "fps", "width", "height", "duration_secs", "frames_count", "positive", "negative", "seed", "scenes",)
    FUNCTION = "expose_play_data"

    CATEGORY = CATEGORY

    def expose_play_data(self, play=None, **kwargs):
        logging.info("GOT PLAY:")
        logging.info("  -  model in play ? " + str("model" in play))

        if play is None:
            return (None,None,None,None,None,None,)
        else:
            return (
                play["model"],
                play["vae"],
                play["title"],
                play["fps"],
                play["width"],
                play["height"],
                play["duration_secs"],
                play["frames_count"],
                play["positive"],
                play["negative"],
                play["seed"],
                play["scenes"],
            )

# #############################################################################
class fot_Scene:

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "title": ("STRING", {"default": "Scene #1"}),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "filename_part": ("STRING", {"default": "#1"}),
            },
            "optional": {
                "scene_beats_%d" % i: ("SCENE_BEAT",) for i in range(1, 3)
            },
            "hidden": {
                "scene_beats_0": ("SCENE_BEAT",),
            }
        }

    RETURN_TYPES = ("SCENE",)
    RETURN_NAMES = ("scene",)
    FUNCTION = "construct_scene"

    CATEGORY = CATEGORY

    def construct_scene(self, title, positive, negative, filename_part, scene_beats_0=None, **kwargs):
        print("All kwargs:", kwargs)
        
        scene_beats = [kwargs.get("scene_beats_%d" % i, None) for i in range(1, MAX_FLOW_NUM)]

        # ignoring trailing Nuns
        while scene_beats and scene_beats[-1] is None:
            scene_beats.pop()
        # need at least one remaining
        if len(scene_beats) == 0:
            raise ValueError("At least one scene_beats item is required")
        # Check for gaps (no Nuns in the middle)
        if None in scene_beats:
            raise ValueError("Found gap in scene_beats: please defragment!")

        output = {
            "title": title,
            "positive": positive,
            "negative": negative,
            "filename_part": filename_part,
            "scene_beats": scene_beats,
        }
        return (output,)

# #############################################################################
class fot_SceneData:

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
            },
            "optional": {
                "scene":  ("SCENE",),
            },
            "hidden": {
            }
        }

    RETURN_TYPES = ("STRING", "CONDITIONING", "CONDITIONING", "STRING", "INT", "SCENE_BEAT",)
    RETURN_NAMES = ("title", "positive", "negative", "filename_part", "frames_count", "scene_beats",)
    FUNCTION = "expose_scene_data"

    CATEGORY = CATEGORY

    def expose_scene_data(self, scene=None, **kwargs):
        if scene is None:
            return (None,None,None,None,None,None,)
        else:
            return (
                scene["title"],
                scene["positive"],
                scene["negative"],
                scene["filename_part"],
                scene["frames_count"],
                scene["scene_beats"],
            )

# #############################################################################
class fot_SceneBeat:

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "title": ("STRING", {"default": "<Set Title>"}),
                "filename_part": ("STRING", {"default": "b1"}),
                # FIXME how to limit fps to just a well known list
                "duration_secs": ("INT", {"default": 1, "min": 1, "max": 100000, "step": 1}),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "images": ("IMAGE",),
            },
            "optional": {},
            "hidden": {}
        }

    RETURN_TYPES = ("SCENE_BEAT",)
    RETURN_NAMES = ("scene_beats",)
    FUNCTION = "construct_scene_beats"

    CATEGORY = CATEGORY

    def construct_scene_beats(self, title, filename_part, duration_secs, positive, negative, images, **kwargs):
        batches = []
        scene_beat = {
            "title": title,
            "filename_part": filename_part,
            "duration_secs": duration_secs,
            "positive": positive,
            "negative": negative,
            "images": images,
            "batches": batches
        }
        return (scene_beat,)

# #############################################################################
class fot_SceneBeatData:

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
            },
            "optional": {
                "scene_beat":  ("SCENE_BEAT",),
            },
            "hidden": {
            }
        }

    RETURN_TYPES = ("STRING", "INT", "CONDITIONING", "CONDITIONING", "IMAGE", "BATCH")
    RETURN_NAMES = ("title", "duration_secs", "positive", "negative", "images", "batches")
    FUNCTION = "expose_scene_data"

    CATEGORY = CATEGORY

    def expose_scene_data(self, scene_beat=None, **kwargs):
        if scene_beat is None:
            return (
                "Beat is None",
                None,
                None,
                None,
                None,
                None,
            )
        else:
            return (
                scene_beat["title"],
                scene_beat["duration_secs"],
                scene_beat["positive"],
                scene_beat["negative"],
                scene_beat["images"],
                scene_beat["batches"],
            )

# #############################################################################
class fot_BatchData:

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
            },
            "optional": {
                "batch":  ("BATCH",),
            },
            "hidden": {
            }
        }

    RETURN_TYPES = ("INT", "INT", "INT", "INT", "STRING",)
    RETURN_NAMES = ("index_play", "frames_count", "frames_first", "frames_last", "filename")
    FUNCTION = "expose_scene_data"

    CATEGORY = CATEGORY

    def expose_scene_data(self, batch=None, **kwargs):
        if batch is None:
            return (None, None, None, None)
        else:
            return (
                batch["index_play"],
                batch["frames_count"],
                batch["frames_first"],
                batch["frames_last"],
                batch["filename"],
            )

# #############################################################################
# this is a modified comfyui-easy-use:whileLoopEnd
class fot_PlayContinue:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        inputs = {
            "required": {
                "flow": ("FLOW_CONTROL", {"rawLink": True}),
                "data": (any_type,),
            },
            "optional": {
            },
            "hidden": {
                "do_continue": ("BOOLEAN", {}),
                "dynprompt": "DYNPROMPT",
                "unique_id": "UNIQUE_ID",
                "extra_pnginfo": "EXTRA_PNGINFO",
            }
        }
        # for i in range(MAX_FLOW_NUM):
        #     inputs["optional"]["initial_value%d" % i] = (any_type,)
        return inputs

    RETURN_TYPES = tuple([any_type]) # ByPassTypeTuple(tuple([any_type] * MAX_FLOW_NUM))
    RETURN_NAMES = tuple(["data"]) # ByPassTypeTuple(tuple(["value%d" % i for i in range(MAX_FLOW_NUM)]))
    FUNCTION = "while_loop_close"

    CATEGORY = CATEGORY

    def explore_dependencies(self, node_id, dynprompt, upstream, parent_ids):
        node_info = dynprompt.get_node(node_id)
        if "inputs" not in node_info:
            return

        for k, v in node_info["inputs"].items():
            if is_link(v):
                parent_id = v[0]
                display_id = dynprompt.get_display_node_id(parent_id)
                display_node = dynprompt.get_node(display_id)
                class_type = display_node["class_type"]
                if class_type not in ['fot_forLoopEnd', 'fot_PlayContinue']:
                    parent_ids.append(display_id)
                if parent_id not in upstream:
                    upstream[parent_id] = []
                    self.explore_dependencies(parent_id, dynprompt, upstream, parent_ids)

                upstream[parent_id].append(node_id)

    def explore_output_nodes(self, dynprompt, upstream, output_nodes, parent_ids):
        for parent_id in upstream:
            display_id = dynprompt.get_display_node_id(parent_id)
            for output_id in output_nodes:
                id = output_nodes[output_id][0]
                if id in parent_ids and display_id == id and output_id not in upstream[parent_id]:
                    if '.' in parent_id:
                        arr = parent_id.split('.')
                        arr[len(arr)-1] = output_id
                        upstream[parent_id].append('.'.join(arr))
                    else:
                        upstream[parent_id].append(output_id)

    def collect_contained(self, node_id, upstream, contained):
        if node_id not in upstream:
            return
        for child_id in upstream[node_id]:
            if child_id not in contained:
                contained[child_id] = True
                self.collect_contained(child_id, upstream, contained)

    def while_loop_close(self, flow, data, dynprompt=None, unique_id=None,**kwargs):
        print("### while_loop_close")
        print(f"* data = {data}")

        data += 1
        print(f"* updated data = {data}")
        do_continue = data < 5
        print(f"* do_continue ? {do_continue}")

        if not do_continue:
            # We're done with the loop
            values = [data]
            # for i in range(MAX_FLOW_NUM):
            #     values.append(kwargs.get("initial_value%d" % i, None))
            return tuple(values)

        # We want to loop
        this_node = dynprompt.get_node(unique_id)
        upstream = {}
        # Get the list of all nodes between the open and close nodes
        parent_ids = []
        self.explore_dependencies(unique_id, dynprompt, upstream, parent_ids)
        parent_ids = list(set(parent_ids))
        # Get the list of all output nodes between the open and close nodes
        prompts = dynprompt.get_original_prompt()
        output_nodes = {}
        for id in prompts:
            node = prompts[id]
            if "inputs" not in node:
                continue
            class_type = node["class_type"]
            class_def = ALL_NODE_CLASS_MAPPINGS[class_type]
            if hasattr(class_def, 'OUTPUT_NODE') and class_def.OUTPUT_NODE == True:
                for k, v in node['inputs'].items():
                    if is_link(v):
                        output_nodes[id] = v

        graph = GraphBuilder()
        self.explore_output_nodes(dynprompt, upstream, output_nodes, parent_ids)
        contained = {}
        open_node = flow[0]
        self.collect_contained(open_node, upstream, contained)
        contained[unique_id] = True
        contained[open_node] = True

        for node_id in contained:
            original_node = dynprompt.get_node(node_id)
            node = graph.node(original_node["class_type"], "Recurse" if node_id == unique_id else node_id)
            node.set_override_display_id(node_id)
        for node_id in contained:
            original_node = dynprompt.get_node(node_id)
            node = graph.lookup_node("Recurse" if node_id == unique_id else node_id)
            for k, v in original_node["inputs"].items():
                if is_link(v) and v[0] in contained:
                    parent = graph.lookup_node(v[0])
                    node.set_input(k, parent.out(v[1]))
                else:
                    node.set_input(k, v)

        new_open = graph.lookup_node(open_node)
        new_open.set_input("data", data)
        # for i in range(MAX_FLOW_NUM):
        #     key = "initial_value%d" % i
        #     new_open.set_input(key, kwargs.get(key, None))
        my_clone = graph.lookup_node("Recurse")
        # result = map(lambda x: my_clone.out(x), range(MAX_FLOW_NUM))

        print("### END while_loop_close")
        return {
            "result": tuple([my_clone.out(0)]),
            "expand": graph.finalize(),
        }


# #############################################################################
NODE_CLASS_MAPPINGS = {
    "fot_Play": fot_Play,
    "fot_PlayData": fot_PlayData,
    "fot_Scene": fot_Scene,
    "fot_SceneData": fot_SceneData,
    "fot_SceneBeat": fot_SceneBeat,
    "fot_SceneBeatData": fot_SceneBeatData,
    "fot_BatchData": fot_BatchData,
    "fot_PlayContinue": fot_PlayContinue,

    "fot_whileLoopStart": fot_whileLoopStart,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "fot_Play": "Play (Start)",
    "fot_PlayData": "Play Data",
    "fot_Scene": "Scene",
    "fot_SceneData": "Scene Data",
    "fot_SceneBeat": "Scene-Beat",
    "fot_SceneBeatData": "Scene-Beat Data",
    "fot_BatchData": "Batch Data",
    "fot_PlayContinue": "Play (Continue)",
}
