import { app } from "../../scripts/app.js";

const WIDGET_NAME_BACKDROP = "backdrop_name";

let common_extension = null;

const findUpstreamWorkspace = async function (node) {
    const DEBUG = false;
    if (DEBUG) console.log("[",node.id,"] findUpstreamWorkspace:");
    if (DEBUG) console.log("[",node.id,"]   - node: ", node);
    const slotIndex = node.findInputSlot("workspace");
    if (slotIndex == -1) {
        if (DEBUG) console.log("[",node.id,"]   > no workspace input slot");
        return;
    }
    const inputLink = node.getInputLink(slotIndex);
    if (!inputLink) {
        if (DEBUG) console.log("[",node.id,"]   > workspace input slot not connected");
        return node;
    }

    if (DEBUG) console.log("[",node.id,"]   > workspace links to ", inputLink.origin_id);
    const upstreamNode = node.graph.getNodeById(inputLink.origin_id);

    if (upstreamNode.type === "fot_Folder") {
        if (DEBUG) console.log("[",node.id,"]   > ", inputLink.origin_id, " is a fot_Folder, moving in");
        return findUpstreamWorkspace(upstreamNode);
    }

    if (upstreamNode.type.startsWith("fot_Workspace")) {
        if (DEBUG) console.log("[",node.id,"]   > ", inputLink.origin_id, " is a fot_Workspace*");
        const upstreamSlotIndex = upstreamNode.findInputSlot("workspace");
        if (upstreamSlotIndex !== -1) {
            const upstreamInputLink = upstreamNode.getInputLink(upstreamSlotIndex);
            if (upstreamInputLink) {
                if (DEBUG) console.log("[",node.id,"]   > workspace is linked, recursing to ", upstreamNode.id);
                return findUpstreamWorkspace(upstreamNode);
            }
            if (DEBUG) console.log("[",node.id,"]   > workspace is not linked");
        }
        else {
            if (DEBUG) console.log("[",node.id,"]   > no workspace input slot for ", upstreamNode.id);
        }

        return upstreamNode;
    }

    if (upstreamNode.type === "Reroute") {
        if (DEBUG) console.log("[",node.id,"]   > upstream node (",upstreamNode.id,") is a reroute: ", upstreamNode);
        const upstreamSlotIndex = upstreamNode.findInputSlot("");
        if (upstreamSlotIndex !== -1) {
            if (DEBUG) console.log("[",node.id,"]   > upstream reroute node (",upstreamNode.id,") has an '' input slot (",upstreamSlotIndex,")");
            const nextUpstreamNodeIdOrNode = upstreamNode.getInputNode(upstreamSlotIndex);
            if (DEBUG) console.log("[",node.id,"]   > upstream reroute node (",upstreamNode.id,") '' input node: ", nextUpstreamNodeIdOrNode);
            if (nextUpstreamNodeIdOrNode) {
                let nextUpstreamNode;
                if (typeof nextUpstreamNodeIdOrNode === "number") {
                    nextUpstreamNode = node.graph.getNodeById(nextUpstreamNodeIdOrNode);
                }
                else {
                    nextUpstreamNode = nextUpstreamNodeIdOrNode;
                }
                if (DEBUG) console.log("[",node.id,"]   > recursing upstream to ", nextUpstreamNode.id);
                return findUpstreamWorkspace(nextUpstreamNode);
            }
            else {
                if (DEBUG) console.log("[",node.id,"]   > upstream reroute node (",upstreamNode.id,") is not linked");
                return null;
            }
        }
        else {
            if (DEBUG) console.log("[",node.id,"]   > upstream reroute node (",upstreamNode.id,") has no '' input slot");
            return null;
        }
    }

    throw new Error("Unexpected, workspace is not a fot_Workspace* or a Reroute! it is a " + upstreamNode.type);
};

const findDownstreamNodes = async function (node) {
    const slotIndex = node.findOutputSlot("workspace");
    if (slotIndex == -1) {
        return [];
    }
    const outputNodes = node.getOutputNodes(slotIndex);
    // console.log(" - outputNodes = ", outputNodes);

    if (outputNodes === null) {
        return [];
    }

    const mynodes = outputNodes.filter((node) => node.type.startsWith("fot_"))
    // console.log(" - mynodes = ", mynodes);

    let downstreamNodes = []
    for (const node of mynodes) {
        const downstreams = await findDownstreamNodes(node);
        downstreamNodes = downstreamNodes.concat([node]).concat(downstreams);
    }

    // console.log(" - downstream nodes = ", mynodes);
    return downstreamNodes;
};

const refreshBackdrops = async function (node) {
    // console.log("updateFolders, node: ", node);
    // Find the folder widget and change it to dropdown
    const folderWidget = node.widgets.find(w => w.name === WIDGET_NAME_BACKDROP);
    if (folderWidget && folderWidget.type !== "combo") {
        // Convert string input to dropdown
        folderWidget.type = "combo";
        folderWidget.options.values = []; // Will be populated dynamically
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

app.registerExtension({
    name: "comyui_play_traversal.extension_common",

    async beforeRegisterNodeDef(nodeType, node, app) {
        if (common_extension) return;
        // console.log("register ", this.name);
        common_extension = this;

        const original_app_graph_configure = app.graph.configure;
        app.graph.configure = async function (graph) {
            let original_app_graph_configure_result;
            // console.log("##### app.graph.configure: ", arguments);
            // console.log("====> this: ", this);
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

                console.log("node added, will refresh backdrops")
                await refreshBackdrops(node);

                return original_onNodeAdded_result;
            };

            // setup existing nodes
            // console.log("##### setup existing nodes: ", graph);
            for (var i = 0, l = graph.nodes.length; i < l; i++) {
                var node = graph.nodes[i];
                if (node.type !== "fot_SceneBackdropData") continue;
                const fullNode = app.graph.getNodeById(node.id);
                // console.log("setup existing node, refresh backdrops: ", fullNode.id);
                await refreshBackdrops(fullNode);
            }

            return original_app_graph_configure_result;
        };
    }
});

app.registerExtension({
    name: "comyui_play_traversal.fot_SceneBackdropData",

    async beforeRegisterNodeDef(nodeType, nodeSpecs, app) {
        if (nodeSpecs.name !== "fot_SceneBackdropData") return;
        // console.log("(", nodeSpecs.id, ") register ", this.name);

        nodeSpecs.input.required.backdrop_name = [[]]

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        const onExecuted = nodeType.prototype.onExecuted;
        const onConfigure = nodeType.prototype.onConfigure;

        nodeType.prototype.onNodeCreated = function () {
            // console.log("onNodeCreated: ", this.id, this);
            const node = this;
            // Find the folder widget and change it to dropdown
            const folderWidget = this.widgets.find(w => w.name === WIDGET_NAME_BACKDROP);
            if (folderWidget && folderWidget.type !== "combo") {
                // console.log(" - changing to combo list", folderWidget);
                folderWidget.type = "combo";
                // folderWidget.options.values = []; // Will be populated dynamically on configure
                folderWidget.options.values = ["Loading..."];
                folderWidget.value = "Loading...";
                this.inputs[1].type = "COMBO";
                // console.log(" - changed to combo list", folderWidget);
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
            // console.log("onConfigure: ", this.id);
            // console.log(" - this: ", this);
            // console.log(" - node: ", node);

            // listen to incoming workspace changes
            const originalOnInputChanged = node.onInputChanged;
            const thiz = this;
            node.onInputChanged = async function () {
                throw new Error("were about to delete this? think again! it IS fired sometimes");
                // if (originalOnInputChanged) originalOnInputChanged.apply(this, arguments);
                // console.log("(", node.id, ") onInputChanged: will update backdrops");
                // await refreshBackdrops(thiz);
            };

            // console.log("(", node.id, ") onConfigure: will update backdrops");
            await refreshBackdrops(this);

            onConfigure?.apply(this, arguments);
        }

        nodeType.prototype.onExecuted = async function (result) {
            await refreshBackdrops(this);
            onExecuted?.apply(this, arguments);
        };

    }
});
