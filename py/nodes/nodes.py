from typing import Iterator, List, Tuple, Dict, Any, Union, Optional
from _decimal import Context, getcontext
from nodes import PreviewImage, SaveImage, NODE_CLASS_MAPPINGS as ALL_NODE_CLASS_MAPPINGS
from ..libs.utils import AlwaysEqualProxy, ByPassTypeTuple, cleanGPUUsedForce, compare_revision
from datetime import datetime
import json
import math

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

class fot_test_NoneModel:
    @classmethod
    def INPUT_TYPES(s):
        return {}

    RETURN_TYPES = ("MODEL",)
    RETURN_NAMES = ("model",)
    FUNCTION = "execute"
    CATEGORY = CATEGORY

    def execute(self):
        return (None,)

class fot_test_NoneVAE:
    @classmethod
    def INPUT_TYPES(s):
        return {}

    RETURN_TYPES = ("VAE",)
    RETURN_NAMES = ("vae",)
    FUNCTION = "execute"
    CATEGORY = CATEGORY

    def execute(self):
        return (None,)

class fot_test_NoneConditioning:
    @classmethod
    def INPUT_TYPES(s):
        return {}

    RETURN_TYPES = ("CONDITIONING",)
    RETURN_NAMES = ("cond",)
    FUNCTION = "execute"
    CATEGORY = CATEGORY

    def execute(self):
        return (None,)

class fot_test_NoneImage:
    @classmethod
    def INPUT_TYPES(s):
        return {}

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "execute"
    CATEGORY = CATEGORY

    def execute(self):
        return (None,)

# #############################################################################
# this is a modified comfyui-easy-use:whileLoopStart
class fot_PlayStart:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        inputs = {
            "required": {
                "model": ("MODEL",),
                "vae": ("VAE",),
                "title": ("STRING", {"default": "Play title"}),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff, "control_after_generate": True, "tooltip": "The random seed used for creating the noise."}),
                "filename_base": ("STRING", {"default": "fot_play"}),
                # TODO how to limit fps to just a well known list
                "fps":  ("FLOAT", {"default": 20, "min": 1, "max": 100000, "step": 1}),
                "width":  ("INT", {"default": 480, "min": 1, "max": 100000, "step": 8}),
                "height":  ("INT", {"default": 832, "min": 1, "max": 100000, "step": 8}),
                "frames_count_per_batch":  ("INT", {"default": 41, "min": 1, "max": 100000, "step": 1}),
            },
            "optional": {
                "data": (any_type,),
            },
            "hidden": {
                "sequence_batches": (any_type,),
                "do_continue": ("BOOLEAN", {"default": True}),
            }
        }
        for i in range(1, 3):
            inputs["optional"]["scene_%d" % i] = ("SCENE",)
        return inputs

    RETURN_TYPES = ("FLOW_CONTROL", "BATCH", any_type, "MODEL", "VAE", "PLAY", "SCENE", "SCENE_BEAT", "BATCH",)
    RETURN_NAMES = ("flow", "sequence_batches", "data", "model", "vae", "play_current", "scene_current", "beat_current", "batch_current",)
    FUNCTION = "play_start"

    CATEGORY = CATEGORY

    def play_start(self, model, vae, title, positive, negative, seed, filename_base, fps, width, height, frames_count_per_batch, data=None, sequence_batches=None, do_continue=True, **kwargs):
        print("### fot_PlayStart")
        print(f"* do_continue = {do_continue}")
        print(f"* data = {data}")

        if sequence_batches is None or len(sequence_batches) == 0:
            # we're just starting, make data into sequence
            print(f"* will construct new play")

            play = {
                "data": data,
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

            logging.info(" == traversing tree for sequencing")

            sequence_batches = []
            duration_secs_play = 0
            index_play = 0

            for scene in scenes:
                scene["filename_base"] = filename_base + "_" + scene["filename_part"]

                scene_beats_list = scene.get("scene_beats", [])
                frames_count_scene = 0
                for scene_beat in scene_beats_list:
                    scene_beat["filename_base"] = scene["filename_base"] + "_" + scene_beat["filename_part"]
                    duration_secs_play += scene_beat["duration_secs"]
                    scene_beat["frames_count"] = int(fps * scene_beat["duration_secs"])
                    batch_count = math.floor(scene_beat["frames_count"] / frames_count_per_batch)
                    remaining_count = scene_beat["frames_count"]
                    last_frame = 0
                    for i in range(0, batch_count):
                        sequence_batch = {
                            "play": play,
                            "scene": scene,
                            "beat": scene_beat,
                            "index_play": index_play,
                            "index": i,
                            "filename": scene_beat["filename_base"] + "_" + str(i) + "_" + str(index_play),
                            "frames_count": frames_count_per_batch,
                        }
                        index_play += 1
                        sequence_batch["frames_first"] = last_frame + 1
                        last_frame = sequence_batch["frames_first"] + frames_count_per_batch - 1
                        sequence_batch["frames_last"] = last_frame

                        sequence_batches.append(sequence_batch)
                        remaining_count = remaining_count - frames_count_per_batch
                    if remaining_count > 0:
                        i = batch_count
                        sequence_batch = {
                            "play": play,
                            "scene": scene,
                            "beat": scene_beat,
                            "index_play": index_play,
                            "index": i,
                            "filename": scene_beat["filename_base"] + "_" + str(i) + "_" + str(index_play),
                            "frames_count": remaining_count,
                        }
                        index_play += 1
                        sequence_batch["frames_first"] = last_frame + 1
                        last_frame = sequence_batch["frames_first"] + remaining_count - 1
                        sequence_batch["frames_last"] = last_frame
                        sequence_batches.append(sequence_batch)

                    frames_count_scene += scene_beat["frames_count"]

                scene["frames_count"] = frames_count_scene

            frames_count_total = int(fps * duration_secs_play)

            play["duration_secs"] = duration_secs_play
            play["frames_count"] = frames_count_total
        else:
            print(f"* will continue existing play")

        print(f"* sequence_batches = {len(sequence_batches)}")

        batch_current = sequence_batches.pop(0)
        # print(f"* batch = {batch_current}")

        beat_current = batch_current["beat"]
        scene_current = batch_current["scene"]
        play_current = batch_current["play"]

        print("### END play_start")

        return tuple(["stub", sequence_batches, data, model, vae, play_current, scene_current, beat_current, batch_current])

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

    RETURN_TYPES = ("MODEL","VAE", "STRING", "FLOAT", "INT", "INT", "INT", "INT", "CONDITIONING", "CONDITIONING", "INT",)
    RETURN_NAMES = ("model", "vae", "title", "fps", "width", "height", "duration_secs", "frames_count", "positive", "negative", "seed",)
    FUNCTION = "expose_play_data"

    CATEGORY = CATEGORY

    def expose_play_data(self, play=None, **kwargs):
        if play is None:
            return (None,None,None,None,None,None,None,None,None,None,None,)
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

    RETURN_TYPES = ("STRING", "CONDITIONING", "CONDITIONING", "STRING", "INT",)
    RETURN_NAMES = ("title", "positive", "negative", "filename_part", "frames_count",)
    FUNCTION = "expose_scene_data"

    CATEGORY = CATEGORY

    def expose_scene_data(self, scene=None, **kwargs):
        if scene is None:
            return (None,None,None,None,None,)
        else:
            return (
                scene["title"],
                scene["positive"],
                scene["negative"],
                scene["filename_part"],
                scene["frames_count"],
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
            },
            "optional": {
                "images": ("IMAGE",),
            },
            "hidden": {}
        }

    RETURN_TYPES = ("SCENE_BEAT",)
    RETURN_NAMES = ("scene_beats",)
    FUNCTION = "construct_scene_beats"

    CATEGORY = CATEGORY

    def construct_scene_beats(self, title, filename_part, duration_secs, positive, negative, images=None, **kwargs):
        scene_beat = {
            "title": title,
            "filename_part": filename_part,
            "duration_secs": duration_secs,
            "positive": positive,
            "negative": negative,
            "images": images,
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

    RETURN_TYPES = ("STRING", "INT", "CONDITIONING", "CONDITIONING", "IMAGE",)
    RETURN_NAMES = ("title", "duration_secs", "positive", "negative", "images",)
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
            )
        else:
            return (
                scene_beat["title"],
                scene_beat["duration_secs"],
                scene_beat["positive"],
                scene_beat["negative"],
                scene_beat["images"],
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
                "sequence_batches": (any_type,),
            },
            "optional": {
                "data": (any_type,),
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
                if class_type not in ['fot_PlayStart', 'fot_PlayContinue']:
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

    def while_loop_close(self, flow, data, sequence_batches, dynprompt=None, unique_id=None,**kwargs):
        print("### fot_PlayContinue")
        print(f"* data = {data}")

        open_node = flow[0]

        do_continue = not sequence_batches is None and len(sequence_batches) > 0
        print(f"* do_continue ? {do_continue}")

        if not do_continue:
            # We're done with the loop
            values = [data]
            # new_open = graph.lookup_node(open_node)
            # new_open.set_input("data", data)
            # new_open.set_input("sequence_batches", sequence_batches)            
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
        new_open.set_input("sequence_batches", sequence_batches)
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
    "fot_PlayStart": fot_PlayStart,
    "fot_PlayData": fot_PlayData,
    "fot_Scene": fot_Scene,
    "fot_SceneData": fot_SceneData,
    "fot_SceneBeat": fot_SceneBeat,
    "fot_SceneBeatData": fot_SceneBeatData,
    "fot_BatchData": fot_BatchData,
    "fot_PlayContinue": fot_PlayContinue,

    "fot_test_NoneModel": fot_test_NoneModel,
    "fot_test_NoneVAE": fot_test_NoneVAE,
    "fot_test_NoneConditioning": fot_test_NoneConditioning,
    "fot_test_NoneImage": fot_test_NoneImage,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "fot_PlayStart": "Play (Start)",
    "fot_PlayData": "Play Data",
    "fot_Scene": "Scene",
    "fot_SceneData": "Scene Data",
    "fot_SceneBeat": "Scene-Beat",
    "fot_SceneBeatData": "Scene-Beat Data",
    "fot_BatchData": "Batch Data",
    "fot_PlayContinue": "Play (Continue)",
}
