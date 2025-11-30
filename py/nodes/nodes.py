from typing import Iterator, List, Tuple, Dict, Any, Union, Optional
from _decimal import Context, getcontext
from nodes import NODE_CLASS_MAPPINGS as ALL_NODE_CLASS_MAPPINGS
from datetime import datetime
import json
import math
import copy
import folder_paths
import os
from pathlib import Path
from PIL import Image, ImageOps, ImageSequence
import numpy as np
import node_helpers
import torch
import comfy.samplers

try: # flow
    from comfy_execution.graph_utils import GraphBuilder, is_link
except:
    GraphBuilder = None

from ..libs.image_io import loadImage, loadMask, loadJson, storeImage, storeMask, storeImageLatent, loadImageLatent

import logging
logger = logging.getLogger('comfyui_play_traversal_logger')
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()

logger.addHandler(handler)

CATEGORY = "Feller of Trees/Play Traversal"

MY_CLASS_TYPES = ['fot_PlayStart', 'fot_PlayContinue']

DEFAULT_FLOW_NUM = 2
MAX_FLOW_NUM = 5

# #############################################################################
# start code from comfyui-easy-use

class AlwaysEqualProxy(str):
    def __eq__(self, _):
        return True

    def __ne__(self, _):
        return False

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

# end code from comfyui-easy-use
# #############################################################################

def remove_nones(list, name):
    # ignoring trailing Nones
    while list and list[-1] is None:
        list.pop()
    # need at least one remaining
    if len(list) == 0:
        raise ValueError(f"At least one {name} is required")
    # Check for gaps (no Nones in the middle)
    if None in list:
        raise ValueError(f"Found gap in {name}s, please defragment!")
    return list

def construct_sequence_batches(model, clip, vae, title, positive, negative, seed, filename_base, fps, width, height, frames_count_per_batch, play_acts, data=None):
    play = {
        "data": data,
        "model": model,
        "clip": clip,
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
    
    play_acts = remove_nones(play_acts, "act")

    print(" == traversing tree for sequencing")

    sequence_batches = []
    duration_secs_play = 0
    index_play = 0

    for play_act in play_acts:
        print(f"  - act: {play_act['title']}")
        play_act["filename_base"] = filename_base + "_" + play_act["filename_part"]
        scenes = play_act.get("scenes", [])
        for scene in scenes:
            print(f"    - scene: {scene['title']}")

            scene["filename_base"] = play_act["filename_base"] + "_" + scene["filename_part"]

            scene_beats_list = scene.get("scene_beats", [])
            frames_count_scene = 0
            for scene_beat in scene_beats_list:
                print(f"      * beat: {scene_beat['title']}")
                print(f"        length: {scene_beat['duration_secs']}")

                scene_beat["filename_base"] = scene["filename_base"] + "_" + scene_beat["filename_part"]
                duration_secs_play += scene_beat["duration_secs"]
                print(f"        duration: {scene_beat['duration_secs']}")
                scene_beat["frames_count"] = int(fps * scene_beat["duration_secs"])
                print(f"        frames: {scene_beat['frames_count']}")
                batch_count = math.floor(scene_beat["frames_count"] / frames_count_per_batch)
                print(f"        batches: {batch_count}")
                remaining_count = scene_beat["frames_count"]
                last_frame = 0
                for i in range(0, batch_count):
                    sequence_batch = {
                        "play": play,
                        "act": play_act,
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
                    print(f"          -> {sequence_batch['filename']}: {sequence_batch['frames_first']} , {sequence_batch['frames_last']}")

                    remaining_count = remaining_count - frames_count_per_batch
                if remaining_count > 0:
                    i = batch_count
                    sequence_batch = {
                        "play": play,
                        "act": play_act,
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
                    print(f"          +> {sequence_batch}")

                frames_count_scene += scene_beat["frames_count"]

            scene["frames_count"] = frames_count_scene
        # play_act[""] = 

    frames_count_total = int(fps * duration_secs_play)

    play["duration_secs"] = duration_secs_play
    play["frames_count"] = frames_count_total

    return sequence_batches

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
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "title": ("STRING", {"default": "Play title"}),
                "positive": ("STRING",),
                "negative": ("STRING",),
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
                "act_current": ("PLAY_ACT",),
                "scene_current": ("SCENE",),
                "beat_current": ("SCENE_BEAT",), 
                "batch_current": ("BATCH",),
                "latent_previous": ("LATENT",),
                "do_continue": ("BOOLEAN", {"default": True}),
                "flow": ("FLOW_CONTROL", {"rawLink": True}),
                "dynprompt": "DYNPROMPT",
                "unique_id": "UNIQUE_ID",
                "extra_pnginfo": "EXTRA_PNGINFO",
            }
        }
        for i in range(1, 3):
            inputs["optional"]["act_%d" % i] = ("PLAY_ACT",)
        return inputs

    RETURN_TYPES = ("FLOW_CONTROL", "BATCH", any_type, "MODEL", "CLIP", "VAE", "PLAY", "PLAY_ACT", "SCENE", "SCENE_BEAT", "BATCH", "LATENT",)
    RETURN_NAMES = ("flow", "sequence_batches", "data", "model", "clip", "vae", "play_current", "act_current", "scene_current", "beat_current", "batch_current", "latent_previous")
    FUNCTION = "play_start"

    CATEGORY = CATEGORY

    def play_start(self, model, clip, vae, title, positive, negative, seed, filename_base, fps, width, height, frames_count_per_batch, data=None, latent_previous=None, sequence_batches=None, play_current=None, act_current=None, scene_current=None, beat_current=None, batch_current=None, do_continue=True, flow=None, dynprompt=None, unique_id=None, **kwargs):
        print("\n>> fot_PlayStart")
        print(f"* do_continue ? {do_continue}")
        # print(f"* data = {data}")
        print(f"* sequence_batches ? {None if sequence_batches is None else len(sequence_batches)}")

        if batch_current is None:
            # we're just starting, make data into sequence
            print(f"* will construct new play")
            play_acts = [kwargs.get("act_%d" % i, None) for i in range(1, 3)]
            sequence_batches = construct_sequence_batches(model, clip, vae, title, positive, negative, seed, filename_base, fps, width, height, frames_count_per_batch, play_acts, data=None)

            print(f"created batches: '{len(sequence_batches)}")
            for batch in sequence_batches:
                print(f" - [ {batch['frames_first']} , {batch['frames_last']} ]")

            batch_current = sequence_batches.pop(0)
            beat_current = batch_current["beat"]
            scene_current = batch_current["scene"]
            act_current = batch_current["act"]
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
        act_title = act_current["title"]
        print(f"* act_current = {act_title}")
        play_title = play_current["title"]
        print(f"* play_current = {play_title}")

        print(">> END play_start")

        return tuple(["stub", sequence_batches, data, model, clip, vae, play_current, act_current, scene_current, beat_current, batch_current])

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
                "latent_previous": ("LATENT",),
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
        print(f"      - filename = {batch_current['filename']}")
        # if not latent_previous is None:
        batch_current["latent_previous"] = latent_previous
        
        beat_current = batch_current["beat"]
        beat_title = beat_current["title"]
        print(f"* beat_current = {beat_title}")

        scene_current = batch_current["scene"]
        scene_title = scene_current["title"]
        print(f"* scene_current = {scene_title}")

        act_current = batch_current["act"]
        act_title = act_current["title"]
        print(f"* act_current = {act_title}")

        play_current = batch_current["play"]
        play_title = play_current["title"]
        print(f"* play_current = {play_title}")

        new_open = graph.lookup_node(open_node)

        new_open.set_input("batch_current", batch_current)
        new_open.set_input("beat_current", beat_current)
        new_open.set_input("scene_current", scene_current)
        new_open.set_input("act_current", act_current)
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

    RETURN_TYPES = ("MODEL", "CLIP", "VAE", "STRING", "FLOAT", "INT", "INT", "INT", "INT", "STRING", "STRING", "INT",)
    RETURN_NAMES = ("model", "clip", "vae", "title", "fps", "width", "height", "duration_secs", "frames_count", "positive", "negative", "seed",)
    FUNCTION = "expose_data"

    CATEGORY = CATEGORY

    def expose_data(self, play=None, **kwargs):
        if play is None:
            return (None,None,None,None,None,None,None,None,None,None,None,None,)
        else:
            return (
                play["model"],
                play["clip"],
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
class fot_PlayAct:

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "title": ("STRING", {"default": "Act #1"}),
                "positive": ("STRING",),
                "negative": ("STRING",),
                "filename_part": ("STRING", {"default": "#1"}),
            },
            "optional": {
                "scene_%d" % i: ("SCENE",) for i in range(1, 3)
            },
            "hidden": {
                "scene_0": ("SCENE",),
            }
        }

    RETURN_TYPES = ("PLAY_ACT",)
    RETURN_NAMES = ("act",)
    FUNCTION = "construct_data"

    CATEGORY = CATEGORY

    def construct_data(self, title, positive, negative, filename_part, scene_0=None, **kwargs):
        
        scenes = [kwargs.get("scene_%d" % i, None) for i in range(1, MAX_FLOW_NUM)]
        scenes = remove_nones(scenes, "scene")

        output = {
            "title": title,
            "positive": positive,
            "negative": negative,
            "filename_part": filename_part,
            "scenes": scenes,
        }

        return (output,)

# #############################################################################
class fot_PlayActData:

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
            },
            "optional": {
                "act":  ("PLAY_ACT",),
            },
            "hidden": {
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "INT",)
    RETURN_NAMES = ("title", "positive", "negative", "filename_part", "frames_count",)
    FUNCTION = "expose_data"

    CATEGORY = CATEGORY

    def expose_data(self, act=None, **kwargs):
        print("act is None ?", act is None)
        if act is None:
            return (None,None,None,None,None,)
        else:
            return (
                act["title"],
                act["positive"],
                act["negative"],
                act["filename_part"],
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
                "positive": ("STRING",),
                "negative": ("STRING",),
                "filename_part": ("STRING", {"default": "#1"}),
            },
            "optional": {
                "scene_beat_%d" % i: ("SCENE_BEAT",) for i in range(1, 3)
            },
            "hidden": {
                "scene_beat_0": ("SCENE_BEAT",),
            }
        }

    RETURN_TYPES = ("SCENE",)
    RETURN_NAMES = ("scene",)
    FUNCTION = "construct_data"

    CATEGORY = CATEGORY

    def construct_data(self, title, positive, negative, filename_part, scene_beat_0=None, **kwargs):
        
        scene_beats = [kwargs.get("scene_beat_%d" % i, None) for i in range(1, MAX_FLOW_NUM)]
        scene_beats = remove_nones(scene_beats, "scene beat")

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

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "INT",)
    RETURN_NAMES = ("title", "positive", "negative", "filename_part", "frames_count",)
    FUNCTION = "expose_data"

    CATEGORY = CATEGORY

    def expose_data(self, scene=None, **kwargs):
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
class fot_SceneBackdrop:

    def __init__(self):
        self.compress_level = 4
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "workspace": ( "WORKSPACE", ),
                "name": ( "STRING", {"default": "backdrop"}, ),
            },
            "optional": {
                "positive": ( "STRING", {"default": ""}, ),
                "negative": ( "STRING", {"default": ""}, ),
                "image": ( "IMAGE", ),
                "image_latent": ( "LATENT", ),
                "image_depthmap": ( "IMAGE", ),
                "seed": ( "INT", {"default": 0}, ),
            },
            "hidden": {
            }
        }

    RETURN_TYPES = ()
    RETURN_NAMES = ()
    FUNCTION = "construct_data"
    OUTPUT_NODE = True

    CATEGORY = CATEGORY

    def construct_data(self, workspace, name, positive="", negative="", image=None, image_latent=None, image_depthmap=None, seed=0, **kwargs):

        home_dir = folder_paths.get_output_directory() # get_user_directory()
        workspaces_dir = os.path.join(home_dir, 'workspaces')
        workspace_dir = os.path.join(workspaces_dir, workspace["codename"])
        scene_backdrops_dir = os.path.join(workspace_dir, "scene_backdrops")
        scene_backdrop_dir = os.path.join(scene_backdrops_dir, name)

        Path(scene_backdrop_dir).mkdir(parents=True, exist_ok=True)

        image_path = None
        if not image is None:
            print("will encode and save image")
            image_path = os.path.join(scene_backdrop_dir, "backdrop.png")
            storeImage(image, image_path)

        image_latent_path = None
        if not image_latent is None:
            print("will encode and save image latent")
            image_latent_path = os.path.join(scene_backdrop_dir, "backdrop_latent.pt")
            storeImageLatent(image_latent, image_latent_path)

        image_depthmap_path = None
        if not image_depthmap is None:
            print("will encode and save image")
            image_depthmap_path = os.path.join(scene_backdrop_dir, "backdrop_depthmap.png")
            storeImage(image_depthmap, image_depthmap_path)

        # save backdrop json
        json_path = os.path.join(scene_backdrop_dir, "backdrop.json")
        backdrop = {
            "name": name,
            "positive": positive,
            "negative": negative,
            "seed": seed,
            "image_path": image_path,
            "image_latent_path": image_latent_path,
            "image_depthmap_path": image_depthmap_path,
        }
        
        try:
            with open(json_path, 'w') as f:
                json.dump(backdrop, f, indent=2)
        except IOError as e:
            print(f" - Error saving {json_path}: {e}")

        # output = {
        #     "name": name,
        #     "positive": positive,
        #     "negative": negative,
        #     "image": image,
        #     "image_path": image_path,
        # }
        # return (output,)
        return ()

# #############################################################################
class fot_SceneBackdropData:

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "workspace": ( "WORKSPACE", ),
                "backdrop_name": ("STRING", {"default": "", "forceInput": False}),
            },
            "optional": {
            },
            "hidden": {
            }
        }

    RETURN_TYPES = ("STRING","STRING","STRING","IMAGE","STRING","LATENT","STRING","MASK","IMAGE","STRING","INT",)
    RETURN_NAMES = ("name","positive","negative","image","image_path","image_latent","image_latent_path","image_mask","image_depthmap","image_depthmap_path","image_seed",)
    FUNCTION = "expose_data"

    CATEGORY = CATEGORY

    def expose_data(self, workspace, backdrop_name=None, **kwargs):
        if backdrop_name is None:
            return (None,None,None,None,None,None,None,None,None,None,None,)
        else:
            workspace_codename = workspace["codename"]
            # load backdrop data
            home_dir = folder_paths.get_output_directory() # get_user_directory()
            workspaces_dir = os.path.join(home_dir, 'workspaces')
            workspace_dir = os.path.join(workspaces_dir, workspace_codename)
            backdrops_dir = os.path.join(workspace_dir, "scene_backdrops")
            backdrop_dir = os.path.join(backdrops_dir, backdrop_name)
            backdrop_json_filename = os.path.join(backdrop_dir, 'backdrop.json')

            scene_backdrop = None
            if os.path.exists(backdrop_json_filename):
                try:
                    with open(backdrop_json_filename, 'r') as f:
                        scene_backdrop = json.load(f)
                except (json.JSONDecodeError, IOError) as e:
                    print(f" - Error loading workspace.json: {e}, creating new one")
            else:
                raise FileNotFoundError(f"Could not find backdrop file: {backdrop_json_filename}")

            image_path = scene_backdrop["image_path"]
            if not image_path is None:
                image, image_mask = loadImage(image_path)

            image_latent_path = scene_backdrop["image_latent_path"]
            if not image_latent_path is None:
                image_latent = loadImageLatent(image_latent_path)

            image_depthmap_path = scene_backdrop["image_depthmap_path"]
            if not image_depthmap_path is None:
                image_depthmap, image_depthmap_mask = loadImage(image_depthmap_path)

            return (
                scene_backdrop["name"],
                scene_backdrop["positive"],
                scene_backdrop["negative"],
                image,
                scene_backdrop["image_path"],
                image_latent,
                scene_backdrop["image_depthmap_path"],
                image_mask,
                image_depthmap,
                scene_backdrop["image_depthmap_path"],
                scene_backdrop["seed"],
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
                "duration_secs": ("FLOAT", {"default": 1, "min": 1, "max": 100000, "step": 0.5}),
                "positive": ("STRING",),
                "negative": ("STRING",),
            },
            "optional": {
            },
            "hidden": {}
        }

    RETURN_TYPES = ("SCENE_BEAT",)
    RETURN_NAMES = ("scene_beats",)
    FUNCTION = "construct_data"

    CATEGORY = CATEGORY

    def construct_data(self, title, filename_part, duration_secs, positive, negative, **kwargs):
        output = {
            "title": title,
            "filename_part": filename_part,
            "duration_secs": duration_secs,
            "positive": positive,
            "negative": negative,
        }
        return (output,)

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

    RETURN_TYPES = ("STRING", "INT", "STRING", "STRING",)
    RETURN_NAMES = ("title", "duration_secs", "positive", "negative",)
    FUNCTION = "expose_data"

    CATEGORY = CATEGORY

    def expose_data(self, scene_beat=None, **kwargs):
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
    FUNCTION = "expose_data"

    CATEGORY = CATEGORY

    def expose_data(self, batch=None, **kwargs):
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
NODE_CLASS_MAPPINGS = {
    "fot_PlayStart": fot_PlayStart,
    "fot_PlayData": fot_PlayData,
    "fot_PlayContinue": fot_PlayContinue,

    "fot_PlayAct": fot_PlayAct,
    "fot_PlayActData": fot_PlayActData,

    "fot_Scene": fot_Scene,
    "fot_SceneData": fot_SceneData,
    "fot_SceneBackdrop": fot_SceneBackdrop,
    "fot_SceneBackdropData": fot_SceneBackdropData,

    "fot_SceneBeat": fot_SceneBeat,
    "fot_SceneBeatData": fot_SceneBeatData,

    "fot_BatchData": fot_BatchData,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "fot_PlayStart": "Play (Start)",
    "fot_PlayData": "Play Data",
    "fot_PlayContinue": "Play (Continue)",

    "fot_PlayAct": "Play-Act",
    "fot_PlayActData": "Play-Act Data",

    "fot_Scene": "Scene",
    "fot_SceneData": "Scene Data",
    "fot_SceneBackdrop": "Scene Backdrop",
    "fot_SceneBackdropData": "Scene Backdrop Data",

    "fot_SceneBeat": "Scene-Beat",
    "fot_SceneBeatData": "Scene-Beat Data",

    "fot_BatchData": "Batch Data",
}
