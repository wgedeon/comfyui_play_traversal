import { app } from "../../scripts/app.js";

const WIDGET_NAME_BACKDROP = "backdrop_name";


const refreshBackdrops = async function (node) {
    // console.log("updateFolders, node: ", node);
    // Find the folder widget and change it to dropdown
    const folderWidget = node.widgets.find(w => w.name === WIDGET_NAME_BACKDROP);
    if (folderWidget && folderWidget.type !== "combo") {
        // Convert string input to dropdown
        folderWidget.type = "combo";
        folderWidget.options.values = []; // Will be populated dynamically
    }

    if (node.workspace_codename) {
        console.log("refreshBackdrops, node.workspace_codename = ", node.workspace_codename);
    }
    else {
        console.log("refreshBackdrops, node.workspace_codename is not set!");
        return;
    }

    // console.log("refreshBackdrops, findUpstreamWorkspace: ", node.id);
    let upstreamNode = await findUpstreamWorkspace(node);

    let workspace_codename = undefined;
    // console.log(" - upstreamNode: ", upstreamNode);
    // if (upstreamNode != null) console.log(" - upstreamNode.workspace_codename: ", upstreamNode.workspace_codename);
    if (upstreamNode != null && upstreamNode.workspace_codename) {
        workspace_codename = upstreamNode.workspace_codename;
    }

    // console.log("(", node.id, ") update folders, workspace_codename: ", workspace_codename);
    node.workspace_codename = workspace_codename;
    if (workspace_codename == undefined) {
        return;
    }

    try {
        const url = `/comfyui_play_traversal/get_backdrops?workspace_codename=${encodeURIComponent(workspace_codename)}`
        const response = await fetch(url);
        const data = await response.json();

        if (response.ok) {
            const widget = node.widgets.find(w => w.name === WIDGET_NAME_BACKDROP);
            // console.log("(", node.id, ") got backdrops: ", data.value)
            const currentValue = widget.value;
            widget.options.values = data.value.sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
            selectBackdrop(node, currentValue);
        }
        else {
            console.error("Server error:", data.error);
        }
    }
    catch (error) {
        console.error("Failed to fetch workspace folders:", error);
    }

};

const selectBackdrop = function (node, backdrop_name) {
    // console.log("(", node.id, ") will select backdrop: ", backdrop_name);
    // console.log("(", node.id, ")   - node: ", node);

    const widget = node.widgets.find(w => w.name === WIDGET_NAME_BACKDROP);
    const folders = widget.options.values;
    if (folders.includes(backdrop_name)) {
        widget.value = backdrop_name;
    }
    else if (folders.length > 0) {
        widget.value = folders[0];
    }
    else {
        widget.value = "default";
    }
    node.setDirtyCanvas(true, false);
};

let extension_common_singleton = null;
app.registerExtension({
    name: "comyui_play_traversal.extension_common_singleton",

    async beforeRegisterNodeDef(nodeType, node, app) {
        if (extension_common_singleton) return;
        const DEBUG = false;
        if (DEBUG) console.log("register extension ", this.name);
        extension_common_singleton = this;

        const original_app_graph_configure = app.graph.configure;
        app.graph.configure = async function (graph) {
            let original_app_graph_configure_result;
            if (DEBUG) console.log("##### app.graph.configure: ", arguments);
            if (DEBUG) console.log("====> this: ", this);
            if (original_app_graph_configure) {
                original_app_graph_configure_result = original_app_graph_configure.apply(this, arguments);
            }

            const original_onNodeAdded = this.onNodeAdded;
            this.onNodeAdded = async function (node) {
                let original_onNodeAdded_result;
                if (original_onNodeAdded) {
                    original_onNodeAdded_result = original_onNodeAdded.apply(this, arguments);
                }
                if (node.type !== "fot_SceneBackdropData") return original_onNodeAdded_result;

                if (DEBUG) console.log("node added, will refresh backdrops")
                await refreshBackdrops(node);

                return original_onNodeAdded_result;
            };

            // setup existing nodes
            if (DEBUG) console.log("##### setup existing nodes: ", graph);
            for (var i = 0, l = graph.nodes.length; i < l; i++) {
                var node = graph.nodes[i];
                if (node.type !== "fot_SceneBackdropData") continue;
                const fullNode = app.graph.getNodeById(node.id);
                if (DEBUG) console.log("setup existing node, refresh backdrops: ", fullNode.id);
                await refreshBackdrops(fullNode);
            }

            return original_app_graph_configure_result;
        };
    }
});

// comyui_play_traversal.fot_SceneBackdropData
app.registerExtension({
    name: "comyui_play_traversal.fot_SceneBackdropData",

    async beforeRegisterNodeDef(nodeType, nodeSpecs, app) {
        if (nodeSpecs.name !== "fot_SceneBackdropData") return;
        const DEBUG = false;
        if (DEBUG) console.log("register extension ", this.name);

        nodeSpecs.input.required.backdrop_name = [[]]

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        const onExecuted = nodeType.prototype.onExecuted;
        const onConfigure = nodeType.prototype.onConfigure;

        nodeType.prototype.onNodeCreated = function () {
            if (DEBUG) console.log("onNodeCreated: ", this.id, this);
            const node = this;
            // Find the folder widget and change it to dropdown
            const folderWidget = this.widgets.find(w => w.name === WIDGET_NAME_BACKDROP);
            if (folderWidget && folderWidget.type !== "combo") {
                if (DEBUG) console.log(" - changing to combo list", folderWidget);
                folderWidget.type = "combo";
                if (DEBUG) folderWidget.options.values = [];
                folderWidget.options.values = ["Loading..."];
                folderWidget.value = "Loading...";
                this.inputs[1].type = "COMBO";
                if (DEBUG) console.log(" - changed to combo list", folderWidget);
            }

            this.addCustomWidget({
                name: "⟳ Refresh",
                title: "⟳ Refresh",
                type: "button",
                callback: async () => {
                    console.log("refresh use reauest: will update backdrops");
                    await refreshBackdrops(node);
                },
            });

            if (onNodeCreated) onNodeCreated.apply(this, arguments);
        };

        nodeType.prototype.onConfigure = async function (node) {
            if (DEBUG) console.log("onConfigure: ", this.id);
            if (DEBUG) console.log(" - this: ", this);
            if (DEBUG) console.log(" - node: ", node);

            if (DEBUG) console.log("(", node.id, ") onConfigure: will update backdrops");
            await refreshBackdrops(this);

            onConfigure?.apply(this, arguments);
        }

        nodeType.prototype.onExecuted = async function (result) {
            await refreshBackdrops(this);
            onExecuted?.apply(this, arguments);
        };

    }
});
