# ComfyUI_Play_Traversal

Provides a structured model and helper nodes for producing long video sequences on ComfyUI using low vram machines.

This work was not started from scratch, it contains copies of bits and pieces from the following awesome projects:

* xx

* xx

* xx

## Purpose

* Produce a sequence of very short videos (2-3s)

* Each part of the process must fit on GPU (8g VRAM)

* Provide a structured narrative tree, sharing conditionings that are in common

## Scene construction (input model)

* the **Play** is the full length of the production; it holds the parameters that are common to the full project; it is made of:

* **Scene**s, there is transition between scenes -- a change in locations, the introduction of a new character...

* Scenes are sequences of **Beat**s, which is a general emotional and energetic state of the scene, the remainder of the layout beeing similar, the background music may be different as well. A scene has a length in seconds.

* In order to fit the processing power of the underlying machine, a scene beat is broken down into a sequence of **Batch**es, each batch covering a part of the beat.

## Helper nodes

* **Play (Start)** paired with **Play (Continue)**: Looping over the batches, and serving the parameters and streams to the body of the loop.

