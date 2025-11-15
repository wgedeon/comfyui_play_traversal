__version__ = "1.0.0"

import yaml
import json
import os
import folder_paths
import importlib

import server
from aiohttp import web
from pathlib import Path

cwd_path = os.path.dirname(os.path.realpath(__file__))
comfy_path = folder_paths.base_path

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
WEB_DIRECTORY = "./js"

# importlib.import_module('.py.routes', __name__)
# importlib.import_module('.py.server', __name__)

# Nodes
nodes_list = [
    "nodes", 
]
for module_name in nodes_list:
    imported_module = importlib.import_module(".py.nodes.{}".format(module_name), __name__)
    NODE_CLASS_MAPPINGS = {**NODE_CLASS_MAPPINGS, **imported_module.NODE_CLASS_MAPPINGS}
    NODE_DISPLAY_NAME_MAPPINGS = {**NODE_DISPLAY_NAME_MAPPINGS, **imported_module.NODE_DISPLAY_NAME_MAPPINGS}

@server.PromptServer.instance.routes.get("/comfyui_play_traversal/get_backdrops")
async def get_backdrops(request):
    """
    Custom endpoint to fetch the backdrop names in a workspace.
    """
    try:
        home_dir = folder_paths.get_output_directory() # get_user_directory()
        workspaces_dir = os.path.join(home_dir, 'workspaces')
        workspace_codename = request.query.get('workspace_codename')
        workspace_dir = os.path.join(workspaces_dir, workspace_codename)
        backdrops_dir = os.path.join(workspace_dir, "scene_backdrops")

        try:
            backdrop_folders = [entry.name for entry in Path(backdrops_dir).iterdir() 
                    if entry.is_dir() and not entry.name.startswith('.')]
            if len(backdrop_folders) == 0:
                backdrop_folders = [ ]
        except OSError as e:
            print(f" - Error reading workspace backdrops: {e}")
            backdrop_folders = [ ]

        return web.json_response({"value": backdrop_folders})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']
