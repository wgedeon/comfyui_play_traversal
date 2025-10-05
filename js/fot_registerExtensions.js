import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

app.registerExtension({
    name: "comyui_play_traversal.fot_test_DisplayInfo",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (!nodeData?.category?.startsWith("Play Traversal (Video)")) {
            return;
        }
        if (nodeData.name === "fot_test_DisplayInfo") {
            const onExecuted = nodeType.prototype.onExecuted;

            nodeType.prototype.onExecuted = function (message) {
                console.log("EXECUTING PROTOTYPE for fot_test_DisplayInfo")

                // if (this.widgets) {
				// 	for (let i = 1; i < this.widgets.length; i++) {
				// 		this.widgets[i].onRemove?.();
				// 	}
				// 	this.widgets.length = 1;
				// }

                // Check if the "text" widget already exists.
                let textWidget = this.widgets && this.widgets.find(w => w.name === "displaytext");
                if (!textWidget) {
                    textWidget = ComfyWidgets["STRING"](this, "displaytext", ["STRING", { multiline: true }], app).widget;
                    textWidget.inputEl.readOnly = true;
                    textWidget.inputEl.style.border = "none";
                    textWidget.inputEl.style.backgroundColor = "transparent";
                }
                textWidget.value = message["text"].join("");
                
                onExecuted?.apply(this, arguments);
            };
        }
        else if (nodeData.name === "fot_NamedReroute") {
            const onExecuted = nodeType.prototype.onExecuted;

            nodeType.prototype.onConfigure = function (arg1, arg2, arg3, arg4) {
                console.log("onConfigure:");
                console.log(" - arg1: ", arg1);
                console.log(" - arg2: ", arg2);
                console.log(" - arg3: ", arg3);
                console.log(" - arg4: ", arg4);
            }

            nodeType.prototype.onExecuted = function (event) {
                console.log("EXECUTING PROTOTYPE for fot_NamedReroute")
                console.log("this: ", this);

                let event_text = event["text"].join("");
                this.title = event_text

                if (this.widgets) {
					for (let i = 1; i < this.widgets.length; i++) {
						console.log(" -- widget: ", this.widgets[i]);
					}
				}

                // Check if the "text" widget already exists.
                let textWidget = this.widgets && this.widgets.find(w => w.name === "displaytext");
                if (!textWidget) {
                    textWidget = ComfyWidgets["STRING"](this, "displaytext", ["STRING", { multiline: true }], app).widget;
                    textWidget.inputEl.readOnly = true;
                    textWidget.inputEl.style.border = "none";
                    textWidget.inputEl.style.backgroundColor = "transparent";
                }
                textWidget.value = event_text;
                
                onExecuted?.apply(this, arguments);
            };
        }

    },
});