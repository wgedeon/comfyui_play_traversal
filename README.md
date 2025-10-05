# ComfyUI_Play_Traversal

Provides a structured model and helper nodes for producing long video sequences on ComfyUI using low vram machines.

## Context

I have started playing with ComfyUI and the video gen space a few months ago. The first obstacle that is still the main on-going challenge is to be able to move out of the gimmick and proof-of-concept, and into a useful activity, on a low VRAM machine.

The iterations culminate with the dream setup I am aiming for: a full Play, fueled with all possible conditioning that's currently available. 

### Requirements

* Provide a structured narrative tree model, sharing conditionings with sub-tree nodes;

* Produce a decent quality long video (longer than 3s) that follows the narrative [1];

* Allow transmission of *what's needed to ensure continuity between video chunks* (probably Noisy Latent Composition [2] and the research concept of "adjacent latent transition mechanisms" [3]).

### Constraints

* Each part of the process must fit on one GPU (8g VRAM) and 32g RAM.

### Nice to have

* To be able to inject actors description (either face images, or a trained LoRA)

* To be able to dictate a pose sequence over a beat, and associate it with a actor.

* To be able to pair sound generation with the different levels of the play (overall recurring base track, specific beat backtrack, actors speech, etc.)

* To be able to generate start (title) and end (credits) scenes.

* To select the actors speech language as part of the Play attributes.

### Standing on the shoulders of giants

This work was not started from scratch, it was inspired by, based on, and, in some cases, contains copies of bits and pieces from those awesome and others:

* The many contributors to platforms such as: [Hugging Face](https://huggingface.co/), and [CivitAI](https://civitai.com/).

* [ComfyUI](https://www.comfy.org/): A highly customisable AI video gen platform providing the users with tools to solve their own problems, using a visual graph construction and execution mecanism; 

* [comfyui-easy-use](https://github.com/yolain/ComfyUI-Easy-Use): Providing quite a few helpful tools/ nodes to make easier the use of ComfyUI;

* [comfyui_essentials](https://github.com/cubiq/ComfyUI_essentials): Backfilling some of the bare necessities in ComfyUI:

* [RES4LYF](https://github.com/ClownsharkBatwing/RES4LYF): Pushing the boundaries of AI video gen with superior quality sampling and many other tools.

## Example workflows

The following sample workflows are included:

* [Empty Body](./workflows/dev_play_loop_empty.json)

* [Ongoing work (does not work)](./workflows/dev_play_loop_current.json)

# Iterations plan

## [<font style="color: green;">stable</font>] Iteration 1: Scene construction (the input model)

### Design

The first step is to define the data model that will drive the video sequence generation loop. I drew inspiration from the theatre play composition:

```mermaid
---
title: Play tree model
---
%%{init: {'theme':'base', 'themeVariables': { 'fontSize': '10px' }}}%%
erDiagram
    direction LR

    PLAY ||--o{ SCENE : has
    SCENE ||--o{ BEAT : has  
    BEAT ||--o{ BATCH : has
```

* the **Play** is the full length of the production; it holds the parameters that are common to the full project; it is made of:

* **Scene**s, there is typically transition between scenes -- a change in locations, the entrance or exit of a character, etc. that would result in crossfade, cut, fade_to_black, etc.

* Scenes are sequences of **Beat**s, which is a general emotional/ mood/ energetic segments of the scene, the remainder of the layout beeing similar (consistent visual and audio characteristics). The background music may be different as well (). A beat has a length in seconds (this is the only video total time length parameter).

beats represent emotional/mood segments with consistent visual and audio characteristics

* In order to fit the processing power of the underlying machine, a scene beat is broken down into a sequence of **Batch**es (batches are technical processing units constrained by hardware limitations), each batch covering a part of the beat, and tailored to the memory limitations (number of frames in the video chunk, number of steps in the sampling).

### Implementation

#### Node `Scene-Beat`

The Scene-Beat is the lowest level `Play` data construction:

![Scene-Beat Node](docs/snaps/scene_beat.png)

> **_TODO:_**  Make optional the negative conditioning input.

#### Node `Scene` 

![Scene-Beat Node](docs/snaps/scene.png)

> **_TODO:_**  Make scene_beats_* a dynamic list input (currently hard-coded limit).

#### Node `Play (Start)`

![Scene-Beat Node](docs/snaps/play.png)

> **_TODO:_**
> * Make scene_* a dynamic list input (currently hard-coded limit).
> * Find a way to make hidden: `sequence_batches`
-----

## [<font style="color: green;">stable</font>] Iteration 2: Batch sequencing (the loop)

### Design

The main idea is to create a sub-graph (the loop body) that takes care of rendering a batch sequence, one batch at a time. All required data must be present as input to the loop body.

The loop starts with `Play (Start)`, and currently provides the following outputs to the loop body:

passed through from the inputs:

* the `model`,

* the `vae`, 

### Implementation

#### Node `Play (Continue)`

Paired with `Play (Start)` using a flow link, the **`Play (Continue)`** marks the end of the loop.
The pair ensures looping over the batches, and serving the parameters and streams to the body of the loop.

![Scene-Beat Node](docs/snaps/loop.png)

The current play data, scene data, beat data, and batch data are available through the following data expansion nodes:

#### Node `Play Data`

![Play Data Node](docs/snaps/play_data.png)


#### Node `Scene Data`

![Scene Data Node](docs/snaps/scene_data.png)


#### Node `Scene-Beat Data`

![Scene-Beat Data Node](docs/snaps/beat_data.png)


#### Node `Batch Data`

![Batch Data Node](docs/snaps/batch_data.png)

## [<font style="color: orange;">in progress</font>] Iteration 3: State transfer

State must be transfered from a previous batch processing step to the current one, in order to 
ensure a smooth batch-to-batch continuity.

* currently investigating the use of `RES4LYF`, still working on the 'state_info' transfer.


## [<font style="color: blue;">next</font>] Iteration 4: Output combine

Preferably within the workflow, potentially:

* not tried: `MergingVideoByTwo` from [MoonHugo/ComfyUI-FFmpeg](https://github.com/MoonHugo/ComfyUI-FFmpeg)

## [<font style="color: orange;">later</font>] Iteration: Define characters with (codename) triggers

* Add `actor` Data capture and expansion, with the attributes:
  - Pre-trained or on-the-fly lora based on character trigger codename (to be used in narrative prompts) and (20-40) image-prompt pairs, based on the character's face features
  - a positive prompt for general behaviour, demeanor, etc.

* Input actors info into play parts, request their rendering based on their codename trigger, e.g. (peter) 

* Use actors in scenes, enter, exit, composition within the scene...

## [<font style="color: orange;">later</font>] Iteration: Use a pose sequence

* input a pose sequence into a beat, associate with actor(s). e.g. a dance quip

# Links to references

* [1] [How to Generate Decent AI Video Without Breaking Your Piggy Bank](https://www.linkedin.com/pulse/how-generate-decent-ai-video-without-breaking-your-piggy-gedeon-lixef)

* [2] [Noisy Latent Composition](https://comfyui-wiki.com/en/workflows/noisy-latent-composition)

* [3] [VideoGen-of-Thought: Step-by-step generating multi-shot video with minimal manual intervention](https://arxiv.org/html/2412.02259v2)
