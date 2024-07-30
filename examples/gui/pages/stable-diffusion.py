# ===----------------------------------------------------------------------=== #
# Copyright (c) 2024, Modular Inc. All rights reserved.
#
# Licensed under the Apache License v2.0 with LLVM Exceptions:
# https://llvm.org/LICENSE.txt
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ===----------------------------------------------------------------------=== #

import os
import time
from os.path import exists

import numpy as np
import streamlit as st
from diffusers import PNDMScheduler
from max.engine import InferenceSession
from PIL import Image
from shared import (
    cache_dir,
    menu,
    modular_cache_dir,
    run_subprocess_monitor_download,
)
from transformers import CLIPTokenizer

st.set_page_config("Stable Diffusion 1.5", page_icon="🎨")

menu()

"""# 🎨 Stable Diffusion 1.5"""


@st.cache_data
def load_tokenizer(path):
    return CLIPTokenizer.from_pretrained(path)


# Sidebar
num_steps = st.sidebar.number_input("Number of steps", 1, 100, 15)
seed = st.sidebar.number_input("Seed", 0, 255)
guidance_scale_factor = st.sidebar.number_input(
    "Guidance Scale Factor", 0.0, 10.0, 7.5
)
latent_scale_factor = st.sidebar.number_input(
    "Latent Scale Factor", 0.0, 1.0, 0.18215
)
output_height = st.sidebar.number_input("Output Height", 0, 2048, 512)
output_width = st.sidebar.number_input("Output Width", 0, 2048, 512)
latent_width = output_width // 8
latent_height = output_height // 8
latent_channels = 4

model_dir = modular_cache_dir() / "stable-diffusion-1.5"
os.makedirs(model_dir, exist_ok=True)
text_encoder_path = model_dir / "text_encoder" / "model.onnx"
img_decoder_path = model_dir / "vae_decoder" / "model.onnx"
img_diffuser_path = model_dir / "unet" / "model.onnx"
scheduler_path = model_dir / "scheduler" / "scheduler_config.json"
tokenizer_path = model_dir / "tokenizer"

if (
    exists(text_encoder_path)
    and exists(img_decoder_path)
    and exists(img_diffuser_path)
    and exists(scheduler_path)
):
    st.info("Models already downloaded", icon="✅")
else:
    with st.spinner("Downloading models and converting to ONNX"):
        command = [
            "optimum-cli",
            "export",
            "onnx",
            "--model",
            "runwayml/stable-diffusion-v1-5",
            model_dir,
        ]
        folder_path = (
            cache_dir()
            / "huggingface"
            / "hub"
            / "models--runwayml--stable-diffusion-v1-5"
            / "blobs"
        )
        run_subprocess_monitor_download(
            command,
            folder_path,
            total_size_mb=5228,
            post_process_msg="Converting models to ONNX",
        )

# Main Page
prompt = st.text_input("Prompt", "A puppy playing the drums")
negative_prompt = st.text_input("Negative Prompt", "No overlapping geometry")

if seed > 0:
    np.random.seed(seed)

if st.button("Generate Image"):
    with st.spinner("Compiling models, faster after first run..."):
        # Need a small delay so the spinner starts correctly
        time.sleep(1)
        session = InferenceSession()
        txt_encoder = session.load(text_encoder_path)
        img_decoder = session.load(img_decoder_path)
        img_diffuser = session.load(img_diffuser_path)

    with st.spinner("Processing Input"):
        tokenizer = load_tokenizer(tokenizer_path)
        prompt_p = tokenizer(
            prompt, padding="max_length", max_length=tokenizer.model_max_length
        )
        prompt_n = tokenizer(
            negative_prompt,
            padding="max_length",
            max_length=tokenizer.model_max_length,
        )
        input_ids = np.stack((prompt_p.input_ids, prompt_n.input_ids))
        encoder_hidden_states = txt_encoder.execute(input_ids=input_ids)[
            "last_hidden_state"
        ]

    with st.spinner("Initializing Latent"):
        scheduler = PNDMScheduler.from_pretrained(scheduler_path)

        # Note: For onnx, shapes are given in NCHW format.
        latent = np.random.normal(
            size=(1, latent_channels, latent_height, latent_width)
        )
        latent = latent * scheduler.init_noise_sigma
        latent = latent.astype(np.float32)

    # Loop through diffusion model.
    scheduler.set_timesteps(num_steps)
    progress_bar = st.progress(0.0, "Step 1/25")
    for i, t in enumerate(scheduler.timesteps):
        progress_bar.progress(i / num_steps, f"Step {i}/{num_steps}")
        if i == num_steps:
            progress_bar.progress(1.0, "Complete!")

        # Duplicate input and scale based on scheduler.
        sample = np.vstack((latent, latent))
        sample = scheduler.scale_model_input(sample, timestep=t)

        # Execute the diffusion model with bs=2. Both batches have same primary input and
        # timestep, but the encoder_hidden_states (primary prompt vs negative) differs.
        noise_pred = img_diffuser.execute(
            sample=sample,
            encoder_hidden_states=encoder_hidden_states,
            timestep=np.array([t], dtype=np.int64),
        )["out_sample"]

        # Merge conditioned & unconditioned outputs.
        noise_pred_text, noise_pred_uncond = np.split(noise_pred, 2)
        noise_pred = noise_pred_uncond + guidance_scale_factor * (
            noise_pred_text - noise_pred_uncond
        )

        # Merge latent with previous iteration.
        latent = scheduler.step(noise_pred, t, latent).prev_sample

    # Decode finalized latent.
    with st.spinner("Decoding Image"):
        latent = latent * (1 / latent_scale_factor)
        decoded = img_decoder.execute(latent_sample=latent)["sample"]
        image = np.clip(decoded / 2 + 0.5, 0, 1).squeeze()
        image = (image.transpose(1, 2, 0) * 255).astype(np.uint8)
        st.image(Image.fromarray(image, "RGB"))