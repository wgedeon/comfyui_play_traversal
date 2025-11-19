
import cv2
import numpy as np
import torch
import os
import folder_paths
from pathlib import Path
from PIL import Image, ImageOps, ImageSequence
import json
import node_helpers

COMPRESS_LEVEL=4

def loadImage(image_path):
    # start code from comfyui core:LoadImage
    img = node_helpers.pillow(Image.open, image_path)

    output_images = []
    output_masks = []
    w, h = None, None

    excluded_formats = ['MPO']

    for i in ImageSequence.Iterator(img):
        i = node_helpers.pillow(ImageOps.exif_transpose, i)

        if i.mode == 'I':
            i = i.point(lambda i: i * (1 / 255))
        image = i.convert("RGB")

        if len(output_images) == 0:
            w = image.size[0]
            h = image.size[1]

        if image.size[0] != w or image.size[1] != h:
            continue

        image = np.array(image).astype(np.float32) / 255.0
        image = torch.from_numpy(image)[None,]
        if 'A' in i.getbands():
            mask = np.array(i.getchannel('A')).astype(np.float32) / 255.0
            mask = 1. - torch.from_numpy(mask)
        elif i.mode == 'P' and 'transparency' in i.info:
            mask = np.array(i.convert('RGBA').getchannel('A')).astype(np.float32) / 255.0
            mask = 1. - torch.from_numpy(mask)
        else:
            mask = torch.zeros((64,64), dtype=torch.float32, device="cpu")
        output_images.append(image)
        output_masks.append(mask.unsqueeze(0))

    if len(output_images) > 1 and img.format not in excluded_formats:
        output_image = torch.cat(output_images, dim=0)
        output_mask = torch.cat(output_masks, dim=0)
    else:
        output_image = output_images[0]
        output_mask = output_masks[0]
    # end code from comfyui core:LoadImage

    return output_image, output_mask

def storeImage(image, image_path, preserve_transparency=True):
    """
    Save image tensor to PNG file
    
    Args:
        image: Tensor in (B, C, H, W) or (C, H, W) format
        image_path: Output file path
        preserve_transparency: If True, maintains alpha channel for 4-channel images
    """
    # Extract first image if batch
    if len(image.shape) == 4:
        img_tensor = image[0]
    else:
        img_tensor = image
    
    img_np = img_tensor.cpu().numpy()
    
    # Handle channel order - ComfyUI uses (C, H, W)
    if len(img_np.shape) == 3 and img_np.shape[0] in [1, 3, 4]:
        img_np = np.transpose(img_np, (1, 2, 0))
    
    img_np = (np.clip(img_np, 0, 1) * 255).astype(np.uint8)
    
    # Determine mode
    if preserve_transparency and img_np.shape[-1] == 4:
        mode = 'RGBA'
    elif img_np.shape[-1] == 3:
        mode = 'RGB'
    elif img_np.shape[-1] == 1:
        mode = 'L'
        img_np = img_np.squeeze(-1)
    else:
        mode = 'L'
    
    img = Image.fromarray(img_np, mode=mode)
    img.save(image_path, compress_level=COMPRESS_LEVEL)
    
    print(f"Image saved: {image_path} (mode: {mode})")

def loadMask(mask_path, invert=False, use_alpha_channel=True):
    """
    Load a mask from PNG file with robust error handling
    
    Args:
        mask_path: Path to the PNG file
        invert: Whether to invert the loaded mask
        use_alpha_channel: If True, uses alpha channel; if False, converts to grayscale
    
    Returns:
        torch.Tensor: Mask tensor in (1, 1, H, W) format
    """
    try:
        print(f"mask_path = ", mask_path)
        # Check if file exists
        if not os.path.exists(mask_path):
            raise FileNotFoundError(f"Mask file not found: {mask_path}")
        
        # Load image
        image = Image.open(mask_path)
        
        if use_alpha_channel:
            # Convert to RGBA to ensure we have alpha channel
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            
            # Extract alpha channel (where storeMask put the mask)
            alpha_channel = np.array(image.split()[-1])
            mask_np = alpha_channel.astype(np.float32) / 255.0
        else:
            # Convert to grayscale and use luminance as mask
            gray_image = image.convert('L')
            mask_np = np.array(gray_image).astype(np.float32) / 255.0
        
        # Apply inversion
        if invert:
            mask_np = 1.0 - mask_np
        
        # Convert to tensor with proper dimensions
        mask_tensor = torch.from_numpy(mask_np).unsqueeze(0)  # (1, H, W)
        
        print(f"Mask loaded from: {mask_path}")
        print(f"  - Dimensions: {mask_tensor.shape}")
        print(f"  - Inverted: {invert}")
        print(f"  - Value range: [{mask_tensor.min():.3f}, {mask_tensor.max():.3f}]")
        
        return mask_tensor
        
    except Exception as e:
        print(f"Error loading mask from {mask_path}: {e}")
        raise

def storeMask(mask, mask_path, invert=False):
    # Ensure mask is 2D (H, W) or 3D (1, H, W)
    if len(mask.shape) == 4:
        mask = mask[0]  # Take first batch element
    
    if len(mask.shape) == 3:
        mask = mask[0]  # Take first channel if 3D
    
    # Convert tensor to numpy
    mask_np = mask.cpu().numpy()

    if invert:
        mask_np = 1.0 - mask_np

    # Normalize to 0-255 range
    mask_np = (mask_np * 255).astype(np.uint8)
    
    # Create RGBA image with mask as alpha channel
    height, width = mask_np.shape
    rgba_array = np.zeros((height, width, 4), dtype=np.uint8)
    
    # Set RGB to white (255, 255, 255) and use mask as alpha
    # white mask
    # rgba_array[..., 0] = 255  # Red
    # rgba_array[..., 1] = 255  # Green  
    # rgba_array[..., 2] = 255  # Blue
    rgba_array[..., 3] = mask_np  # Alpha from mask
    
    # Convert to PIL Image
    image = Image.fromarray(rgba_array, 'RGBA')
    
    # Save to output directory
    output_dir = folder_paths.get_output_directory()
    os.makedirs(output_dir, exist_ok=True)
        
    image.save(mask_path, "PNG")
    
    print(f"Mask saved as: {mask_path}")

def loadJson(element_json_filename):
    if os.path.exists(element_json_filename):
        try:
            with open(element_json_filename, 'r') as f:
                character_pose_object = json.load(f)
            return character_pose_object
        except (json.JSONDecodeError, IOError) as e:
            print(f" - Error loading workspace.json: {e}, creating new one")
    else:
        raise FileNotFoundError(f"Could not find element file: {element_json_filename}")
