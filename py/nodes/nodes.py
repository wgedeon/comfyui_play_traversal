from typing import Iterator, List, Tuple, Dict, Any, Union, Optional
from _decimal import Context, getcontext
from nodes import PreviewImage, SaveImage, NODE_CLASS_MAPPINGS as ALL_NODE_CLASS_MAPPINGS
from ..libs.utils import AlwaysEqualProxy, ByPassTypeTuple, cleanGPUUsedForce, compare_revision
from datetime import datetime
import json
import math
import copy

try: # flow
    from comfy_execution.graph_utils import GraphBuilder, is_link
except:
    GraphBuilder = None

import torch
import comfy.samplers
import comfy.sample
import folder_paths
import latent_preview
import node_helpers

import logging
logger = logging.getLogger('comfyui_play_traversal_logger')
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()

logger.addHandler(handler)


CATEGORY = "Play Traversal (Video)"
CATEGORY_SAMPLING = "Play Traversal (Video)/sampling"
CATEGORY_LATENT = "Play Traversal (Video)/latent"
CATEGORY_TEST = "Play Traversal (Video)/test"

MY_CLASS_TYPES = ['fot_PlayStart', 'fot_PlayContinue']

DEFAULT_FLOW_NUM = 2
MAX_FLOW_NUM = 5

any_type = AlwaysEqualProxy("*")


def explore_upstream(node_id, dynprompt, upstream, parent_ids):
    node_info = dynprompt.get_node(node_id)
    if "inputs" not in node_info:
        return

    for k, v in node_info["inputs"].items():
        if is_link(v):
            parent_id = v[0]
            display_id = dynprompt.get_display_node_id(parent_id)
            display_node = dynprompt.get_node(display_id)
            class_type = display_node["class_type"]
            if class_type not in MY_CLASS_TYPES:
                parent_ids.append(display_id)
            if parent_id not in upstream:
                upstream[parent_id] = []
                explore_upstream(parent_id, dynprompt, upstream, parent_ids)

            upstream[parent_id].append(node_id)

def explore_output_nodes(dynprompt, upstream, output_nodes, parent_ids):
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

def collect_contained(node_id, upstream, contained):
    if node_id not in upstream:
        return
    for child_id in upstream[node_id]:
        if child_id not in contained:
            contained[child_id] = True
            collect_contained(child_id, upstream, contained)

def construct_sequence_batches(model, vae, title, positive, negative, seed, filename_base, fps, width, height, frames_count_per_batch, scenes, data=None):
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

    return sequence_batches

class fot_test_NoneModel:
    @classmethod
    def INPUT_TYPES(s):
        return {}

    RETURN_TYPES = ("MODEL",)
    RETURN_NAMES = ("model",)
    FUNCTION = "execute"
    CATEGORY = CATEGORY_TEST

    def execute(self):
        return (None,)

class fot_test_NoneVAE:
    @classmethod
    def INPUT_TYPES(s):
        return {}

    RETURN_TYPES = ("VAE",)
    RETURN_NAMES = ("vae",)
    FUNCTION = "execute"
    CATEGORY = CATEGORY_TEST

    def execute(self):
        return (None,)

class fot_test_NoneConditioning:
    @classmethod
    def INPUT_TYPES(s):
        return {}

    RETURN_TYPES = ("CONDITIONING",)
    RETURN_NAMES = ("cond",)
    FUNCTION = "execute"
    CATEGORY = CATEGORY_TEST

    def execute(self):
        return (None,)

class fot_test_NoneImage:
    @classmethod
    def INPUT_TYPES(s):
        return {}

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "execute"
    CATEGORY = CATEGORY_TEST

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
                "play_current": ("PLAY",),
                "scene_current": ("SCENE",),
                "beat_current": ("SCENE_BEAT",), 
                "batch_current": ("BATCH",),
                "latent_previous": ("LATENT", {}),
                "do_continue": ("BOOLEAN", {"default": True}),
                "flow": ("FLOW_CONTROL", {"rawLink": True}),
                "dynprompt": "DYNPROMPT",
                "unique_id": "UNIQUE_ID",
                "extra_pnginfo": "EXTRA_PNGINFO",
            }
        }
        for i in range(1, 3):
            inputs["optional"]["scene_%d" % i] = ("SCENE",)
        return inputs

    RETURN_TYPES = ("FLOW_CONTROL", "BATCH", any_type, "MODEL", "VAE", "PLAY", "SCENE", "SCENE_BEAT", "BATCH", "LATENT",)
    RETURN_NAMES = ("flow", "sequence_batches", "data", "model", "vae", "play_current", "scene_current", "beat_current", "batch_current", "latent_previous")
    FUNCTION = "play_start"

    CATEGORY = CATEGORY

    def play_start(self, model, vae, title, positive, negative, seed, filename_base, fps, width, height, frames_count_per_batch, data=None, latent_previous=None, sequence_batches=None, play_current=None, scene_current=None, beat_current=None, batch_current=None, do_continue=True, flow=None, dynprompt=None, unique_id=None, **kwargs):
        print("\n>> fot_PlayStart")
        print(f"* do_continue ? {do_continue}")
        # print(f"* data = {data}")
        print(f"* sequence_batches ? {None if sequence_batches is None else len(sequence_batches)}")

        if batch_current is None:
            # we're just starting, make data into sequence
            print(f"* will construct new play")
            scenes = [kwargs.get("scene_%d" % i, None) for i in range(1, 3)]
            sequence_batches = construct_sequence_batches(model, vae, title, positive, negative, seed, filename_base, fps, width, height, frames_count_per_batch, scenes, data=None)

            batch_current = sequence_batches.pop(0)
            beat_current = batch_current["beat"]
            scene_current = batch_current["scene"]
            play_current = batch_current["play"]
        else:
            print(f"* will continue existing play")

        batch_current["latent_previous"] = latent_previous

        batch_index_play = batch_current["index_play"]
        print(f"* batch_current = {batch_index_play}")
        beat_title = beat_current["title"]
        print(f"* beat_current = {beat_title}")
        scene_title = scene_current["title"]
        print(f"* scene_current = {scene_title}")
        play_title = play_current["title"]
        print(f"* play_current = {play_title}")

        print(">> END play_start")

        return tuple(["stub", sequence_batches, data, model, vae, play_current, scene_current, beat_current, batch_current])

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
                "latent_previous": ("LATENT", {}),
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
    FUNCTION = "play_continue"

    CATEGORY = CATEGORY

    def play_continue(self, flow, sequence_batches, latent_previous=None, data=None, dynprompt=None, unique_id=None,**kwargs):
        print("\n|| fot_PlayContinue")
        # print(f"  unique_id = {unique_id}")
        # print(f"* data = {data}")
        print(f"* sequence_batches ? {None if sequence_batches is None else len(sequence_batches)}")

        open_node = flow[0]
        graph = GraphBuilder()
        this_node = dynprompt.get_node(unique_id)

        do_continue = not sequence_batches is None and len(sequence_batches) > 0
        print(f"* do_continue ? {do_continue}")

        if not do_continue:
            # We're done with the loop
            values = [data]

            return tuple(values)
        
        # We want to loop
        upstream = {}
        # Get the list of all nodes between the open and close nodes
        parent_ids = []
        explore_upstream(unique_id, dynprompt, upstream, parent_ids)
        parent_ids = list(set(parent_ids))
        print(f"* parent_ids = {parent_ids}")

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

        explore_output_nodes(dynprompt, upstream, output_nodes, parent_ids)
        contained = {}

        collect_contained(open_node, upstream, contained)
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

        batch_current = sequence_batches.pop(0)
        batch_index_play = batch_current["index_play"]
        print(f"* batch_current = {batch_index_play}")
        if not latent_previous is None:
            batch_current["latent_previous"] = latent_previous
        
        beat_current = batch_current["beat"]
        beat_title = beat_current["title"]
        print(f"* beat_current = {beat_title}")

        scene_current = batch_current["scene"]
        scene_title = scene_current["title"]
        print(f"* scene_current = {scene_title}")

        play_current = batch_current["play"]
        play_title = play_current["title"]
        print(f"* play_current = {play_title}")

        new_open = graph.lookup_node(open_node)

        play_current, scene_current, beat_current, batch_current

        new_open.set_input("batch_current", batch_current)
        new_open.set_input("beat_current", beat_current)
        new_open.set_input("scene_current", scene_current)
        new_open.set_input("play_current", play_current)
        new_open.set_input("data", data)
        new_open.set_input("sequence_batches", sequence_batches)
        new_open.set_input("latent_previous", latent_previous)
        my_clone = graph.lookup_node("Recurse")

        print("|| END fot_PlayContinue\n")
        return {
            "result": tuple([my_clone.out(0)]),
            "expand": graph.finalize(),
        }

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
            },
            "hidden": {}
        }

    RETURN_TYPES = ("SCENE_BEAT",)
    RETURN_NAMES = ("scene_beats",)
    FUNCTION = "construct_scene_beats"

    CATEGORY = CATEGORY

    def construct_scene_beats(self, title, filename_part, duration_secs, positive, negative, **kwargs):
        scene_beat = {
            "title": title,
            "filename_part": filename_part,
            "duration_secs": duration_secs,
            "positive": positive,
            "negative": negative,
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

    RETURN_TYPES = ("STRING", "INT", "CONDITIONING", "CONDITIONING",)
    RETURN_NAMES = ("title", "duration_secs", "positive", "negative",)
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

    RETURN_TYPES = ("INT", "INT", "INT", "INT", "LATENT", "STRING",)
    RETURN_NAMES = ("index_play", "frames_count", "frames_first", "frames_last", "latent_previous", "filename")
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
                batch["latent_previous"],
                batch["filename"],
            )

# #############################################################################
# Start from comfyui_essentials
# #############################################################################

# modified version of comfyui_essentials:misc.DisplayAny
class fot_test_DisplayInfo:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "input": (("*",{})),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(s, input_types):
        return True

    RETURN_TYPES = ("STRING",)
    RETURN_TYPES = ("display",)
    FUNCTION = "execute"
    OUTPUT_NODE = True

    CATEGORY = CATEGORY_TEST

    def add_tensor_shapes(self, tensor, text_array):
        if isinstance(tensor, dict):
            for k in tensor:
                text_array = self.add_tensor_shapes(tensor[k])
        elif isinstance(tensor, list):
            for i in range(len(tensor)):
                text_array = self.add_tensor_shapes(tensor[i])
        elif hasattr(tensor, 'shape'):
            text_array.append(list(tensor.shape))
        return text_array

    def execute(self, input):
        text = []
        if isinstance(input, torch.Tensor):
            text.append("### torch.Tensor:")
            self.add_tensor_shapes(input, text)
        elif isinstance(input, dict):
            text.append("### dict:")
            text = text + [ f"  - {k}: {str(v)}" for k, v in input.items()]
        else:
            text.append(f"### other {type(input).__name__}:")
            text.append(str(input))

        display = "\n".join(text)

        return {"ui": {"text": display}, "result": (display,)}

# #############################################################################
# End from comfyui_essentials
# #############################################################################

# #############################################################################
# Start from RES4LYF
# #############################################################################

# #############################################################################
# this is a modified RES4LYF:latent_transfer_state_info
class fot_LatentTransferStateInfo_Lenient:
    def __init__(self):
        pass
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "latent_to":   ("LATENT", ),      
            },
            "optional": {
                "latent_from": ("LATENT", ),
            }
        }

    RETURN_TYPES = ("LATENT",)
    RETURN_NAMES = ("latent",)
    FUNCTION     = "main"
    CATEGORY     = CATEGORY_LATENT

    def main(self, latent_to, latent_from=None):
        state_info = []
        if not latent_from is None:
            if not 'state_info' in latent_from:
                raise ValueError("No 'state_info' in latent_from")
            state_info = latent_from['state_info']
        latent_to['state_info'] = copy.deepcopy(state_info)
        return (latent_to,)

# #############################################################################
# this is a modified RES4LYF:nodes_latents.latent_display_state_info

class fot_test_DisplayLatent_Lenient:
    def __init__(self):
        pass
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                    "latent": ("LATENT", ),      
                     },
                }

    RETURN_TYPES = ("STRING",)
    FUNCTION     = "execute"
    CATEGORY     = CATEGORY_TEST
    OUTPUT_NODE  = True

    def execute(self, latent):
        text = ""
        if latent is None:
            text = "latent is None"
        elif not 'state_info' in latent:
            text = "No 'state_info' in latent"
        else:
            for key, value in latent['state_info'].items():
                if isinstance(value, torch.Tensor):
                    if value.numel() == 0:
                        value_text = "empty tensor"
                    elif value.numel() == 1:
                        if value.dtype == torch.bool:
                            value_text = f"bool({value.item()})"
                        else:
                            value_text = f"str({value.item():.3f}), dtype: {value.dtype}"
                    else:
                        shape_str = str(list(value.shape)).replace(" ", "")
                        dtype = value.dtype

                        if torch.is_floating_point(value) is False:
                            if value.dtype == torch.bool:
                                value_text = f"shape: {shape_str}, dtype: {dtype}, true: {value.sum().item()}, false: {(~value).sum().item()}"
                            else:
                                max_val = value.float().max().item()
                                min_val = value.float().min().item()
                                value_text = f"shape: {shape_str}, dtype: {dtype}, max: {max_val}, min: {min_val}"
                        else:
                            mean = value.float().mean().item()
                            std = value.float().std().item()
                            value_text = f"shape: {shape_str}, dtype: {dtype}, mean: {mean:.3f}, std: {std:.3f}"
                else:
                    value_text = str(value)

                text += f"{key}: {value_text}\n"

        return {"ui": {"text": text}, "result": (text,)}

# #############################################################################
# End from RES4LYF
# #############################################################################

# #############################################################################
# Start from comfyui core
# #############################################################################
def common_ksampler(model, seed, steps, cfg, sampler_name, scheduler, positive, negative, latent, denoise=1.0, disable_noise=False, start_step=None, last_step=None, force_full_denoise=False):
    latent = latent["samples"]
    latent = comfy.sample.fix_empty_latent_channels(model, latent)

    if disable_noise:
        noise = torch.zeros(latent.size(), dtype=latent.dtype, layout=latent.layout, device="cpu")
    else:
        batch_inds = latent["batch_index"] if "batch_index" in latent else None
        noise = comfy.sample.prepare_noise(latent, seed, batch_inds)

    noise_mask = None
    if "noise_mask" in latent:
        noise_mask = latent["noise_mask"]

    callback = latent_preview.prepare_callback(model, steps)
    disable_pbar = not comfy.utils.PROGRESS_BAR_ENABLED
    samples = comfy.sample.sample(model, noise, steps, cfg, sampler_name, scheduler, positive, negative, latent,
                                  denoise=denoise, disable_noise=disable_noise, start_step=start_step, last_step=last_step,
                                  force_full_denoise=force_full_denoise, noise_mask=noise_mask, callback=callback, disable_pbar=disable_pbar, seed=seed)

    print(f"-- ksampler:")
    print(f"   * 'state_info' in latent ? {'state_info' in latent}")

    out = latent.copy()
    out["samples"] = samples
    return (out, )

# largely based on Comfyui core: KSampler
class fot_SubStepsKSampler:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "model": ("MODEL", { "tooltip": "The model used for denoising the input latent."}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff, "control_after_generate": True, "tooltip": "The random seed used for creating the noise."}),
                "steps": ("INT", {"default": 20, "min": 1, "max": 10000, "tooltip": "The number of steps used in the denoising process."}),
                "cfg": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0, "step":0.1, "round": 0.01, "tooltip": "The Classifier-Free Guidance scale balances creativity and adherence to the prompt. Higher values result in images more closely matching the prompt however too high values will negatively impact quality."}),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS, { "tooltip": "The algorithm used when sampling, this can affect the quality, speed, and style of the generated output."}),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS, { "tooltip": "The scheduler controls how noise is gradually removed to form the image."}),
                "positive": ("CONDITIONING", { "tooltip": "The conditioning describing the attributes you want to include in the image."}),
                "negative": ("CONDITIONING", { "tooltip": "The conditioning describing the attributes you want to exclude from the image."}),
                "latent_image": ("LATENT", { "tooltip": "The latent image to denoise."}),
                "denoise": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01, "tooltip": "The amount of denoising applied, lower values will maintain the structure of the initial image allowing for image to image sampling."}),
            },
            "optional": {
                "step_first": ("INT", { "default": 1, "min": 1, "tooltip": "The first step to sample (must be in [1 .. <code>steps</code>]"}),
                "step_count": ("INT", {"default": -1, "min": -1, "tooltip": "The number of steps to sample (<code>step_first + step_count &lt;= steps</code>, -1 = all remaining)."}),
            } 
        }

    RETURN_TYPES = ("LATENT",)
    OUTPUT_TOOLTIPS = ("The denoised latent.",)
    FUNCTION = "sample"

    CATEGORY = CATEGORY_SAMPLING
    DESCRIPTION = "Uses the provided model, positive and negative conditioning to denoise the latent image. Allows to run partial sub-steps of the denoising process.<br /><b>Note: indexes are 1 based!</b>"

    def sample(self, model, seed, steps, cfg, sampler_name, scheduler, positive, negative, latent_image, step_first=1, step_count=-1, denoise=1.0):
        print(f"## sample")
        print(f"* steps = {steps}")
        print(f"* step_first = {step_first}")
        if step_first < 1:
            raise ValueError("step_first may not be smaller than one")
        start_step = step_first - 1
        print(f"* start_step = {start_step}")
        if step_count == -1:
            step_count = steps - start_step
        print(f"* step_count = {step_count}")
        last_step = start_step + step_count - 1
        print(f"* last_step = {last_step}")
        if last_step > steps:
            # be permissive and restrict to available steps
            # raise ValueError("step_count is too high")
            last_step = steps
            print(f"==> last_step = {last_step}")
        print(f"* 'state_info' in latent ? {'state_info' in latent_image}")
        
        return common_ksampler(model, seed, steps, cfg, sampler_name, scheduler, positive, negative, latent_image, start_step=start_step, last_step=last_step, denoise=denoise)

# #############################################################################
# End from comfyui core
# #############################################################################


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

    "fot_SubStepsKSampler": fot_SubStepsKSampler,

    "fot_LatentTransferStateInfo_Lenient": fot_LatentTransferStateInfo_Lenient,

    "fot_test_DisplayLatent_Lenient": fot_test_DisplayLatent_Lenient,
    "fot_test_DisplayInfo": fot_test_DisplayInfo,
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

    "fot_SubStepsKSampler": "KSampler (Sub-Steps)",

    "fot_LatentTransferStateInfo_Lenient": "Latent Transfer State (Lenient)",

    "fot_test_DisplayLatent_Lenient": "🔧 Display Latent State (Lenient)",
    "fot_test_DisplayInfo": "🔧 Display Info",
    "fot_test_NoneModel": "🔧 No Model",
    "fot_test_NoneVAE": "🔧 No VAE",
    "fot_test_NoneConditioning": "🔧 No Conditioning",
    "fot_test_NoneImage": "🔧 No Image",
}
