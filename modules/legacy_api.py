#Initial API by https://github.com/TomJamesPearce, additional work by Seth A. Robinson

import uvicorn
from fastapi import FastAPI, Body, APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import json
import io
import base64
import gradio as grr
from modules.sd_samplers import samplers, samplers_for_img2img
from PIL import Image, ImageOps
from . import shared
import modules.txt2img
import modules.img2img
import modules.extras
from modules.upscaler import Upscaler, UpscalerData
from modules.shared import opts, cmd_opts, state
import modules.safety as safety
import numpy as np

#needed for Python versions older than 3.9:
from typing import List

#from the aitools dir
from aitools.image_segmentation import DoImageSegmentationAndReturnMask

class TextToImage(BaseModel):
    prompt: str = Field(..., title="Prompt Text", description="The text to generate an image from.")
    negative_prompt: str = Field(default="", title="Negative Prompt Text")
    prompt_style: str = Field(default="None", title="Prompt Style")
    prompt_style2: str = Field(default="None", title="Prompt Style 2")
    steps: int = Field(default=20, title="Steps")
    sampler_index: int = Field(0, title="Sampler Index")
    restore_faces: bool = Field(default=False, title="Restore Faces")
    tiling: bool = Field(default=False, title="Tiling")
    n_iter: int = Field(default=1, title="N Iter")
    batch_size: int = Field(default=1, title="Batch Size")
    cfg_scale: float = Field(default=7, title="Config Scale")
    seed: int = Field(default=-1.0, title="Seed")
    subseed: int = Field(default=-1.0, title="Subseed")
    subseed_strength: float = Field(default=0, title="Subseed Strength")
    seed_resize_from_h: int = Field(default=0, title="Seed Resize From Height")
    seed_resize_from_w: int = Field(default=0, title="Seed Resize From Width")
    seed_enable_extras: bool = Field(default=False, title="Seed enable extras")
    height: int = Field(default=512, title="Height")
    width: int = Field(default=512, title="Width")
    enable_hr: bool = Field(default=False, title="Enable HR")
    scale_latent: bool = Field(default=True, title="Scale Latent")
    denoising_strength: float = Field(default=0.7, title="Denoising Strength")
    
    #these are not part of the real call, but needed to make life easier for the API user
    sampler_name: str = Field(default = "", title="Sampler name", description="Can be used instead of sampler_index") 
    safety_filter: str = Field(default="default", title="Safety filter") #needs to be removed from array later due to the method used to call the func
    alpha_mask_subject: bool = Field(default=False, title="Remove background via alpha channel") #needs to be removed from array later due to the method used to call the func
  
class TextToImageResponse(BaseModel):
    images: List[str] = Field(default=None, title="Image", description="The generated image in base64 format.")
    nsfw_detected: bool = Field(default=None, title="NSFW detected")
    all_prompts: List[str] = Field(default=None, title="All Prompts", description="The prompt text.")
    negative_prompt: str = Field(default=None, title="Negative Prompt Text")
    seed: int = Field(default=None, title="Seed")
    all_seeds: List[int] = Field(default=None, title="All Seeds")
    subseed: int = Field(default=None, title="Subseed")
    all_subseeds: List[int] = Field(default=None, title="All Subseeds")
    subseed_strength: float = Field(default=None, title="Subseed Strength")
    width: int = Field(default=None, title="Width")
    height: int = Field(default=None, title="Height")
    sampler_index: int = Field(default=None, title="Sampler Index")
    sampler: str = Field(default=None, title="Sampler") 
    cfg_scale: float = Field(default=None, title="Config Scale")
    steps: int = Field(default=None, title="Steps")
    batch_size: int = Field(default=None, title="Batch Size")
    restore_faces: bool = Field(default=None, title="Restore Faces")
    face_restoration_model: str = Field(default=None, title="Face Restoration Model")
    sd_model_hash: str = Field(default=None, title="SD Model Hash")
    seed_resize_from_w: int = Field(default=None, title="Seed Resize From Width")
    seed_resize_from_h: int = Field(default=None, title="Seed Resize From Height")
    denoising_strength: float = Field(default=None, title="Denoising Strength")
    extra_generation_params: dict = Field(default={}, title="Extra Generation Params")
    index_of_first_image: int = Field(default=None, title="Index of First Image")
    html: str = Field(default=None, title="HTML")

#note: Instead of copying the exact format of the internal img2img function, I'm doing a simplified version.  
#Mostly because I think I have to decode the images before sending the data to the img2img function so we can't do the
#'send the giant list in' trick anyway, and this should give us all the options needed.

class ImageToImage(BaseModel):
    prompt: str = Field(..., title="Prompt Text", description="The guiding prompt text")
    negative_prompt: str = Field(default="", title="Negative Prompt Text")
    image: str = Field(default=None, title="Image png")
    mask_image: str = Field(default=None, title="Mask png (white means active, black is masked out)")
    steps: int = Field(default=20, title="Steps")
    sampler_index: int = Field(0, title="Sampler Index")
    seed: int = Field(default=-1.0, title="Seed")
    cfg_scale: float = Field(default=7.5, title="Config Scale")
    width: int = Field(default=512, title="Width")
    height: int = Field(default=512, title="Height")
    restore_faces: bool = Field(default=False, title="Restore Faces")
    tiling: bool = Field(default=False, title="Tiling")
    mask_blur: int = Field(default=4, title="Mask Blur")
    denoising_strength: float = Field(default=0.64, title="Denoising Strength")
    sampler_name: str = Field(default = "", title="Sampler name", description="Can be used instead of sampler_index") 
    inpainting_fill: str = Field(default="original", title="Inpainting Fill Mode",  description="Options: fill, original, latent noise, latent nothing")
    safety_filter: str = Field(default="default", title="Safety filter") #if true, will override server settings and return ../aitools/safety_filter.png if nsfw detected
    alpha_mask_subject: bool = Field(default=False, title="After processing, remove background via alpha channel")
    generate_subject_mask: bool = Field(default=False, title="Before processing, create mask of subject and use it")
    generate_subject_mask_reverse: bool = Field(default=False, title="Before processing, create reverse mask of subject and use it")

class Extras(BaseModel):
    image: str = Field(default=None, title="Image to upscale")
    upscaler1_name: str = Field(default = "None", title="Upscaler1 name", description="None, ESRGAN_4x, etc")
    upscaler2_name: str = Field(default = "None", title="Upscaler2 name", description="None, ESRGAN_4x, etc")
    upscaling_resize: float = Field(default=2.0, title="Upscaling resize", description="Set to 2 for 2x original size")
    gfpgan_visibility: float = Field(default=0, title="gfpgan visibility", description="0 to 1, 0 means don't fix faces at all with gfpgan")
    codeformer_visibility: float = Field(default=0, title="Codeformer visibility", description="0 to 1, 0 means don't fix faces at all with Codeformer")
    codeformer_weight: float = Field(default=0, title="Codeformer weight", description="CodeFormer weight (0 = maximum effect, 1 = minimum effect")
    extras_upscaler_2_visibility: float = Field(default=0.5, title="extras_upscaler_2_visibility", description="0 means none, 1 means full")
    alpha_mask_subject: bool = Field(default=False, title="Remove background via alpha channel") 
  

class ExtrasResponse(BaseModel):
    images: List[str] = Field(default=None, title="Image", description="The generated image in base64 format.")
    html: str = Field(default=None, title="HTML")

class ImageToImageResponse(BaseModel):
    images: List[str] = Field(default=None, title="Image", description="The generated image in base64 format.")
    html: str = Field(default=None, title="HTML")
    nsfw_detected: bool = Field(default=None, title="NSFW detected")
 
class Interrogator(BaseModel):
    image: str = Field(default=None, title="Image png")
  
class InterrogatorResponse(BaseModel):
    description: str = Field(default=None, title="Generated description of the image we sent")

def GetSamplerIndexFromName(samplerName):

    for idx, x in enumerate(samplers):
            if x.name == samplerName:
                return idx
    
    print("Error, can't find sampler by name: "+samplerName)
    return -1 #error
       
def GetImg2ImgSamplerIndexFromName(samplerName):

    for idx, x in enumerate(samplers_for_img2img):
            if x.name == samplerName:
                return idx
    
    print("Error, can't find img2img sampler by name: "+samplerName)
    return -1 #error

def GetUpscalerIndexFromName(upscalerName):

    for idx, x in enumerate(shared.sd_upscalers):
            if x.name == upscalerName:
                return idx
    
    print("Error, can't find upscaler by name: "+upscalerName)
    
    return 0 #default to None

def ApplyMaskToImage(inputImage: Image, maskImage: Image):

    #to actually remove the background from the image, we do this:
    #blackImage = Image.new("RGB", inputImage.size, (0, 0, 0))
    #inputImage = Image.composite(inputImage, blackImage, maskImage)
   
    #add the alpha to the image
    inputImage.putalpha(maskImage)
    return inputImage


class LegacyApi:
    def __init__(self, app):
        self.app = app
        self.router = APIRouter()
        self.app.add_api_route("/v1/txt2img", self.txt2imgendpoint, response_model=TextToImageResponse, methods=["POST"])
        self.app.add_api_route("/v1/img2img", self.img2imgendpoint, response_model=ImageToImageResponse, methods=["POST"])
        self.app.add_api_route("/v1/extras", self.extrasendpoint, methods=["POST"])
        #app.add_api_route("/v1/pnginfo", self.pnginfoendpoint, methods=["POST"])
        self.app.add_api_route("/v1/interrogator", self.interrogatorendpoint, methods=["POST"])
        self.app.add_api_route("/aitools/get_info.json", self.get_info)
  
    def txt2imgendpoint(self, txt2imgreq: TextToImage = Body(embed=True)):

        d = txt2imgreq.dict()

        samplerName = d['sampler_name']
     
        if len(samplerName) > 0:
            newSamplerIndex = GetSamplerIndexFromName(samplerName)
            if newSamplerIndex != -1:
                 d['sampler_index'] = newSamplerIndex
        
        #if true, we do our own NSFW check and send back a custom image if nsfw.  If false, we do whatever the server default is
        forceNSFFilter = int(d['safety_filter'].lower() == "true")
        alpha_mask_subject = d['alpha_mask_subject']
    
        #remove things that aren't in original function call.  Should probably just rewrite all of this
        #to manually send in the vars separately as this is getting confusing
        del d['sampler_name']
        del d['safety_filter']
        del d['alpha_mask_subject']

        #for idx, x in enumerate(samplers):
        #    print(f"{x.name}, ")
     
        #print(f"Using sampler {samplers[ d['sampler_index']].name}")
        
        images, params, html = modules.txt2img.txt2img(*[v for v in d.values()], 0, False, None, '', False, 1, '', 4, '', True)
     
        b64images = []
        nsfw_detected = False

        for i in images:
    
            buffer = io.BytesIO()
    
            if forceNSFFilter:
                #this is slightly wasteful as we're converting the image BACK to numpy, but I don't want to return a blank image if nswf is detected, I want
                #to send back a custom image and tag in the json, plus not change safety.py
                x_checked_image, has_nsfw_concept = safety.check_safety(np.array(i))
                if has_nsfw_concept[0]:
                    pngFileToSendBack = "aitools/safety_filter.png"
                    print(f"Uh oh, NSFW content detected, sending back {pngFileToSendBack} instead")
                    Image.open(pngFileToSendBack).save(buffer, format="png");
                    nsfw_detected = True
   
            if not nsfw_detected:

                if alpha_mask_subject:
                    i = ApplyMaskToImage(i, DoImageSegmentationAndReturnMask(i))
            
            i.save(buffer, format="png")
        
            b64images.append(base64.b64encode(buffer.getvalue()))
  

        resp_params = json.loads(params)
      
        return TextToImageResponse(images=b64images, nsfw_detected = nsfw_detected, **resp_params, html=html)

    def img2imgendpoint(self, img2imgreq: ImageToImage = Body(embed=True)):
        d =img2imgreq.dict() #make things more readable

        #inpaintPic = Image.open("aitools/pic.png")
        #inpaintMask = Image.open("aitools/mask.png")
 
        #let's pull our pic and mask out
        if d['image'] != None:
            decodedImage = base64.decodebytes(bytes(d['image'], "utf-8"))
            inpaintPic = Image.open(io.BytesIO(decodedImage))
        else:
            msg = ("Error: no image parm sent in request")
            print(msg)
            return {msg}

        if d['mask_image'] != None:
            decodedImage = base64.decodebytes(bytes(d['mask_image'], "utf-8"))
            inpaintMask = Image.open(io.BytesIO(decodedImage))
        else:
            print("No mask sent, creating default full mask")
            inpaintMask = Image.new("RGB", (inpaintPic.width, inpaintPic.height), (255, 255, 255))


        generate_subject_mask = d['generate_subject_mask']
        generate_subject_mask_reverse = d['generate_subject_mask_reverse']
    
        if generate_subject_mask or generate_subject_mask_reverse:
            print("Using AI to create mask of subject...")
            inpaintMask = DoImageSegmentationAndReturnMask(inpaintPic)
            if generate_subject_mask_reverse:
                inpaintMask = ImageOps.invert(inpaintMask)
                #inpaintMask.save("mask_test.png", format="png")
      

     
        samplerName = d['sampler_name']
        
        if len(samplerName) > 0:
            newSamplerIndex = GetImg2ImgSamplerIndexFromName(samplerName)
            if newSamplerIndex != -1:
                 d['sampler_index'] = newSamplerIndex


        print(f"Using sampler {samplers_for_img2img [ d['sampler_index']].name}")
      
        inpainting_fill_mode = 1 #default is 'original'

        if d['inpainting_fill'] == "fill":
            inpainting_fill_mode = 0
        if d['inpainting_fill'] == "original":
            inpainting_fill_mode = 1
        if d['inpainting_fill'] == "latent noise":
            inpainting_fill_mode = 2
        if d['inpainting_fill'] == "latent nothing":
            inpainting_fill_mode = 3

        #if true, we do our own NSFW check and send back a custom image if nsfw.  If false, we do whatever the server default is
        forceNSFFilter = int(d['safety_filter'].lower() == "true")
        alpha_mask_subject = d['alpha_mask_subject']
        maskAlpha = 1 #a new parm that was just added
        init_img_with_mask_orig = None #this is a new parm, unsure what it does right now, just fixing the build
        images, params, html = modules.img2img.img2img(1, d['prompt'], d['negative_prompt'], "", "", None, {}, init_img_with_mask_orig, inpaintPic, inpaintMask, 1,
        d['steps'], d['sampler_index'], d['mask_blur'], maskAlpha, inpainting_fill_mode,  d['restore_faces'], d['tiling'], 1, 1, d['cfg_scale'], d['denoising_strength'],
        d['seed'], -1, 0, -1, -1, False, d['height'], d['width'], 0, True, 0, False, "", "", 
        0, False, None, '', False, 1, '', 4, '', True)

        #print(F"Ok, got {len(images)} images")

        b64images = []
        nsfw_detected = False
      
        for i in images:
            buffer = io.BytesIO()
    
            if forceNSFFilter:
                #this is slightly wasteful as we're converting the image BACK to numpy, but I don't want to return a blank image if nswf is detected, I want
                #to send back a custom image and tag in the json, plus not change safety.py
                x_checked_image, has_nsfw_concept = safety.check_safety(np.array(i))
                if has_nsfw_concept[0]:
                    pngFileToSendBack = "aitools/safety_filter.png"
                    print(f"Uh oh, NSFW content detected, sending back {pngFileToSendBack} instead")
                    Image.open(pngFileToSendBack).save(buffer, format="png");
                    nsfw_detected = True
              
            if not nsfw_detected:

                if alpha_mask_subject:
                    i = ApplyMaskToImage(i, DoImageSegmentationAndReturnMask(i))
           
                i.save(buffer, format="png")
   
            b64images.append(base64.b64encode(buffer.getvalue()))
        
        resp_params = json.loads(params)
    
        return ImageToImageResponse(images=b64images, nsfw_dectected=nsfw_detected, **resp_params, html=html)

    def extrasendpoint(self, extrasreq: Extras = Body(embed=True)):
        d =extrasreq.dict() #make things more readable
     
       #let's pull our pic out
        if d['image'] != None:
            decodedImage = base64.decodebytes(bytes(d['image'], "utf-8"))
            pic = Image.open(io.BytesIO(decodedImage))
            #pic = pic.convert('RGB') #RGBA will cause a crash, so convert if needed
        else:
            msg = ("Error: no image parm sent in request")
            print(msg)
            return {msg}

        #for idx, x in enumerate(shared.sd_upscalers):
        #   print(f" Upscaler: {idx}: {x.name}")
      
      
        upscaler1_index = GetUpscalerIndexFromName(d['upscaler1_name'])
        upscaler2_index = GetUpscalerIndexFromName(d['upscaler2_name'])

        #print(f"Using upscaler {shared.sd_upscalers[upscaler1_index].name} and {shared.sd_upscalers[upscaler2_index].name}")

#def run_extras(extras_mode, resize_mode, image, image_folder, input_dir, output_dir, show_extras_results, gfpgan_visibility, codeformer_visibility, codeformer_weight, upscaling_resize, upscaling_resize_w, upscaling_resize_h, upscaling_crop, extras_upscaler_1, extras_upscaler_2, extras_upscaler_2_visibility):
  

        images, params, html = modules.extras.run_extras(0, 0, pic, "", "", "", False, d['gfpgan_visibility'],d['codeformer_visibility'],d['codeformer_weight'], 
        d['upscaling_resize'], 1.0, 1.0, 1.0, upscaler1_index, upscaler2_index,d['extras_upscaler_2_visibility'], True)

        alpha_mask_subject = d['alpha_mask_subject']
      
        b64images = []
        for i in images:
          
            if alpha_mask_subject:
                i = ApplyMaskToImage(i, DoImageSegmentationAndReturnMask(i))
       
            buffer = io.BytesIO()
            i.save(buffer, format="png")
            b64images.append(base64.b64encode(buffer.getvalue()))
        
        
        return ExtrasResponse(images=b64images, html=html)

    def pnginfoendpoint(self):
        raise NotImplementedError

    def interrogatorendpoint(self, interrogatorreq: Interrogator = Body(embed=True)):
        
        d =interrogatorreq.dict() #make things more readable
        
        #let's pull our pic out
        if d['image'] != None:
            decodedImage = base64.decodebytes(bytes(d['image'], "utf-8"))
            pic = Image.open(io.BytesIO(decodedImage))
            pic = pic.convert('RGB') #RGBA will cause a crash, so convert if needed
        else:
            msg = ("Error: no image parm sent in request")
            print(msg)
            return {msg}

        prompt = shared.interrogator.interrogate(pic)
      
        return InterrogatorResponse(description=prompt)

  
    def get_info(self):
        #this is just for Seth's server, it allows my client app to understand when it or the server's version is outdated
        #todo:  create json file dynamically, add list of samplers/upscaler names available?
        return FileResponse("aitools/get_info.json")
        

